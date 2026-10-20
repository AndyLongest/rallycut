"""Loopback-only, offline desktop web application and serial inference queue."""

from __future__ import annotations

import argparse
import contextlib
import json
import mimetypes
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit
from urllib.request import Request, urlopen
import uuid
import webbrowser

VERSION = "0.2.0"
MAX_UPLOAD_BYTES = 8 * 1024**3
JOB_ID = re.compile(r"^[a-f0-9]{32}$")
VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".mts", ".m2ts", ".ts"}
TERMINAL = {"completed", "failed", "cancelled"}
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def atomic_json(path: Path, data):
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    os.replace(temp, path)


def configure_environment(root: Path):
    """Keep scratch files and model caches in the distributable's directory."""
    data = root / "data"
    for name in ("temp", "cache", "logs", "jobs"):
        (data / name).mkdir(parents=True, exist_ok=True)
    for variable in ("TEMP", "TMP", "TMPDIR"):
        os.environ[variable] = str(data / "temp")
    for variable in ("XDG_CACHE_HOME", "MPLCONFIGDIR", "YOLO_CONFIG_DIR"):
        os.environ[variable] = str(data / "cache")
    ffmpeg_dirs = [root / "runtime/ffmpeg/bin", root / "runtime/ffmpeg"]
    os.environ["PATH"] = os.pathsep.join(
        [str(p) for p in ffmpeg_dirs if p.is_dir()] + [os.environ.get("PATH", "")]
    )
    os.environ["PYTHONUTF8"] = "1"
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"


def kill_process_tree(process: subprocess.Popen):
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True, timeout=20, creationflags=NO_WINDOW,
        )
    else:
        import signal
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGTERM)
    with contextlib.suppress(subprocess.TimeoutExpired):
        process.wait(timeout=10)
    if process.poll() is None:
        process.kill()


class JobManager:
    def __init__(self, root: Path, *, start_worker=True):
        self.root = root.resolve()
        self.directory = self.root / "data/jobs"
        self.directory.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.wakeup = threading.Event()
        self.stopping = False
        self.jobs = {}
        self.process = None
        self.current_id = None
        self.thread = None
        for directory in self.directory.iterdir():
            if directory.is_dir() and JOB_ID.fullmatch(directory.name):
                job = read_json(directory / "job.json")
                if job and job.get("id") == directory.name:
                    if job["state"] == "running":
                        job.update(state="failed", message="上次处理被中断，请重新上传视频。",
                                   error="程序退出时任务尚未完成。")
                        atomic_json(directory / "job.json", job)
                    self.jobs[job["id"]] = job
        if start_worker:
            self.thread = threading.Thread(target=self._run, name="cpu-job-queue", daemon=True)
            self.thread.start()

    def snapshot(self, job_id):
        with self.lock:
            job = dict(self.jobs[job_id])
            if job["state"] == "running":
                progress = read_json(self.directory / job_id / "progress.json", {})
                for key in ("phase", "progress", "message", "processed_seconds", "total_seconds",
                            "device", "device_message"):
                    if key in progress:
                        job[key] = progress[key]
                job["elapsed_seconds"] = max(0, time.time() - job.get("started_at", time.time()))
            return job

    def list_jobs(self):
        with self.lock:
            return [self.snapshot(key) for key in sorted(
                self.jobs, key=lambda key: self.jobs[key]["created_at"], reverse=True)]

    def enqueue(self, job_id, filename, source_name, size):
        with self.lock:
            if self.stopping:
                raise RuntimeError("程序正在退出。")
            job = dict(id=job_id, filename=filename, source_name=source_name, size_bytes=size,
                       state="queued", phase="queued", progress=0, message="等待前面的任务完成",
                       created_at=time.time(), elapsed_seconds=0)
            atomic_json(self.directory / job_id / "job.json", job)
            self.jobs[job_id] = job
            self.wakeup.set()
            return dict(job)

    def cancel(self, job_id):
        with self.lock:
            job = self.jobs[job_id]
            if job["state"] in TERMINAL:
                return dict(job)
            job.update(state="cancelled", phase="cancelled", message="任务已取消")
            atomic_json(self.directory / job_id / "job.json", job)
            process = self.process if self.current_id == job_id else None
        if process:
            kill_process_tree(process)
        return self.snapshot(job_id)

    def delete(self, job_id):
        with self.lock:
            if self.jobs[job_id]["state"] not in TERMINAL or self.current_id == job_id:
                raise ValueError("请先取消任务，等待处理停止后再删除。")
            target = (self.directory / job_id).resolve()
            if target.parent != self.directory.resolve() or not JOB_ID.fullmatch(job_id):
                raise ValueError("Invalid job directory")
            shutil.rmtree(target)
            del self.jobs[job_id]

    def close(self):
        with self.lock:
            self.stopping = True
            current_id = self.current_id
        if current_id:
            self.cancel(current_id)
        self.wakeup.set()
        if self.thread:
            self.thread.join(timeout=25)

    def _run(self):
        while True:
            with self.lock:
                if self.stopping:
                    return
                queued = sorted(
                    (job for job in self.jobs.values() if job["state"] == "queued"),
                    key=lambda job: job["created_at"],
                )
                job = queued[0] if queued else None
                if job:
                    self.current_id = job["id"]
                    job.update(state="running", phase="preparing", message="正在读取视频",
                               started_at=time.time())
                    directory = self.directory / job["id"]
                    atomic_json(directory / "job.json", job)
            if job is None:
                self.wakeup.wait(1)
                self.wakeup.clear()
                continue
            try:
                command = [sys.executable, "-B", "-X", "utf8", "-m", "rallycut.local_worker", "--root", str(self.root),
                           "--job", str(directory), "--video", str(directory / job["source_name"]),
                           "--filename", job["filename"]]
                env = os.environ.copy()
                # For a development checkout; the embedded runtime uses python312._pth.
                env["PYTHONPATH"] = str(self.root / "src")
                with (directory / "worker.log").open("wb") as log:
                    with self.lock:
                        if job["state"] == "cancelled" or self.stopping:
                            continue
                        self.process = subprocess.Popen(
                            command, cwd=self.root, stdout=log, stderr=subprocess.STDOUT,
                            env=env, creationflags=NO_WINDOW,
                            start_new_session=os.name != "nt",
                        )
                    code = self.process.wait()
                with self.lock:
                    if job["state"] != "cancelled":
                        if code == 0 and (directory / "result.json").is_file() and (directory / "media.mp4").is_file():
                            job.update(state="completed", phase="completed", progress=1,
                                       message="识别完成，可以预览和下载")
                        else:
                            progress = read_json(directory / "progress.json", {})
                            job.update(state="failed", phase="failed",
                                       message="这个视频未能处理完成",
                                       error=progress.get("error") or progress.get("message") or
                                       f"处理进程退出（代码 {code}）。详细信息保存在任务目录的 worker.log。")
            except Exception as exc:
                with self.lock:
                    if job["state"] != "cancelled":
                        job.update(state="failed", phase="failed", message="无法启动处理",
                                   error=str(exc))
            finally:
                with self.lock:
                    job["elapsed_seconds"] = max(0, time.time() - job["started_at"])
                    atomic_json(directory / "job.json", job)
                    self.process = None
                    self.current_id = None


def byte_range(value: str | None, size: int):
    if not value:
        return 0, size - 1, False
    match = re.fullmatch(r"bytes=(\d*)-(\d*)", value.strip())
    if not match or not any(match.groups()) or size <= 0:
        raise ValueError("Invalid range")
    first, last = match.groups()
    if first:
        start = int(first)
        end = min(int(last), size - 1) if last else size - 1
    else:
        count = int(last)
        if count <= 0:
            raise ValueError("Invalid suffix")
        start, end = max(0, size - count), size - 1
    if start >= size or start > end:
        raise ValueError("Unsatisfiable range")
    return start, end, True


class AppServer(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False

    def __init__(self, address, root: Path, manager: JobManager):
        self.root = root
        self.manager = manager
        self.token = secrets.token_urlsafe(32)
        self.upload_lock = threading.Lock()
        super().__init__(address, AppHandler)


class AppHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def setup(self):
        super().setup()
        self.connection.settimeout(90)

    def handle(self):
        try:
            super().handle()
        except (ConnectionResetError, BrokenPipeError, socket.timeout):
            pass  # Browsers routinely close idle or interrupted media sockets.

    def log_message(self, format, *args):
        # Avoid terminal noise for one-second progress polls.
        if len(args) > 1 and str(args[1]).startswith(("4", "5")):
            sys.stderr.write("%s %s\n" % (self.log_date_time_string(), format % args))

    def _reply(self, code, data, *, head=False):
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if not head:
            self.wfile.write(payload)

    def _allowed(self, mutate=False):
        port = self.server.server_port
        hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if self.headers.get("Host") not in hosts:
            self.close_connection = True
            self._reply(403, {"error": "仅支持本机访问。"})
            return False
        origin = self.headers.get("Origin")
        if origin and origin not in {f"http://{host}" for host in hosts}:
            self.close_connection = True
            self._reply(403, {"error": "来源不匹配，请从启动页面访问。"})
            return False
        if mutate and not secrets.compare_digest(
            self.headers.get("X-RallyCut-Token", ""), self.server.token
        ):
            self.close_connection = True
            self._reply(403, {"error": "页面已过期，请刷新后重试。"})
            return False
        return True

    def do_HEAD(self):
        self.do_GET(head=True)

    def do_GET(self, head=False):
        if not self._allowed():
            return
        path = urlsplit(self.path).path
        if path == "/api/config":
            return self._reply(200, dict(token=self.server.token, version=VERSION,
                                        max_upload_bytes=MAX_UPLOAD_BYTES), head=head)
        if path == "/api/health":
            return self._reply(200, {"app": "RallyCut", "version": VERSION}, head=head)
        if path == "/api/jobs":
            return self._reply(200, {"jobs": self.server.manager.list_jobs()}, head=head)
        if path in ("/", "/index.html", "/app.css", "/app.js", "/favicon.svg"):
            name = "index.html" if path == "/" else path[1:]
            return self._file(Path(__file__).parent / "web" / name, head=head)
        parts = path.strip("/").split("/")
        if len(parts) >= 3 and parts[:2] == ["api", "jobs"] and JOB_ID.fullmatch(parts[2]):
            job_id = parts[2]
            try:
                job = self.server.manager.snapshot(job_id)
            except KeyError:
                return self._reply(404, {"error": "任务不存在"}, head=head)
            if len(parts) == 3:
                return self._reply(200, job, head=head)
            directory = self.server.manager.directory / job_id
            if len(parts) == 4 and parts[3] in {"result", "media", "download", "clips.zip"}:
                if job["state"] != "completed":
                    return self._reply(409, {"error": "任务尚未完成"}, head=head)
                names = {"result": "result.json", "download": "result.json",
                         "media": "media.mp4", "clips.zip": "clips.zip"}
                attachment = {"download": "rallies.json", "clips.zip": "rally_clips.zip"}.get(parts[3])
                return self._file(directory / names[parts[3]], head=head, attachment=attachment)
            if len(parts) == 5 and parts[3] == "clips" and re.fullmatch(r"\d{3,6}\.mp4", parts[4]):
                if job["state"] != "completed":
                    return self._reply(409, {"error": "任务尚未完成"}, head=head)
                return self._file(directory / "clips" / ("rally_" + parts[4]), head=head,
                                  attachment="rally_" + parts[4])
        self._reply(404, {"error": "页面或文件不存在"}, head=head)

    def _file(self, path: Path, *, head=False, attachment=None):
        try:
            stream = path.open("rb")
        except OSError:
            return self._reply(404, {"error": "文件不存在"}, head=head)
        with stream:
            size = os.fstat(stream.fileno()).st_size
            try:
                start, end, partial = byte_range(self.headers.get("Range"), size)
            except ValueError:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            length = max(0, end - start + 1)
            self.send_response(206 if partial else 200)
            kind = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            if path.suffix == ".js":
                kind = "text/javascript"
            if path.suffix in {".html", ".css", ".js", ".json", ".svg"}:
                kind += "; charset=utf-8"
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(length))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "same-origin")
            if path.suffix == ".html":
                self.send_header("Content-Security-Policy",
                    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                    "img-src 'self' data:; media-src 'self' blob:; connect-src 'self'; "
                    "object-src 'none'; frame-ancestors 'none'")
            if partial:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            if attachment:
                self.send_header("Content-Disposition", f'attachment; filename="{attachment}"')
            self.end_headers()
            if head:
                return
            stream.seek(start)
            try:
                while length:
                    chunk = stream.read(min(length, 1024 * 1024))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    length -= len(chunk)
            except (BrokenPipeError, ConnectionResetError, socket.timeout):
                pass  # Normal when a video seeks or a download is cancelled.

    def do_POST(self):
        if not self._allowed(mutate=True):
            return
        path = urlsplit(self.path).path
        if path == "/api/jobs":
            return self._upload()
        if path == "/api/shutdown":
            self._reply(200, {"message": "正在关闭"})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        match = re.fullmatch(r"/api/jobs/([a-f0-9]{32})/cancel", path)
        if match:
            try:
                return self._reply(200, self.server.manager.cancel(match[1]))
            except KeyError:
                return self._reply(404, {"error": "任务不存在"})
        self._reply(404, {"error": "操作不存在"})

    def _upload(self):
        try:
            if self.headers.get("Transfer-Encoding"):
                raise ValueError("需要提供文件大小。")
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= MAX_UPLOAD_BYTES:
                raise ValueError("请选择大于 0、且不超过 8 GB 的视频。")
            filename = unquote(self.headers.get("X-File-Name", ""), errors="strict")
            filename = filename.replace("\\", "/").rsplit("/", 1)[-1].strip()
            if not filename or len(filename) > 240 or any(ord(c) < 32 for c in filename):
                raise ValueError("文件名无效。")
            suffix = Path(filename).suffix.lower()
            if suffix not in VIDEO_SUFFIXES:
                raise ValueError("请选择 MP4、MOV、MKV、AVI、WebM 或 TS 视频。")
            if shutil.disk_usage(self.server.root).free < length * 3 + 512 * 1024**2:
                raise ValueError("磁盘剩余空间不足，请为原视频、预览和切片留出空间。")
        except (ValueError, UnicodeError) as exc:
            self.close_connection = True
            return self._reply(400, {"error": str(exc)})
        if not self.server.upload_lock.acquire(blocking=False):
            self.close_connection = True
            return self._reply(409, {"error": "另一个视频正在上传，请稍后再试。"})
        job_id = uuid.uuid4().hex
        directory = self.server.manager.directory / job_id
        try:
            directory.mkdir()
            part = directory / "upload.part"
            remaining = length
            with part.open("wb") as output:
                while remaining:
                    chunk = self.rfile.read(min(remaining, 1024 * 1024))
                    if not chunk:
                        raise ValueError("上传中断，请重试。")
                    output.write(chunk)
                    remaining -= len(chunk)
            source_name = "source" + suffix
            part.rename(directory / source_name)
            job = self.server.manager.enqueue(job_id, filename, source_name, length)
            self._reply(202, job)
        except (OSError, ValueError, RuntimeError) as exc:
            # Delete only this request's new, UUID-named upload directory.
            with self.server.manager.lock:
                saved = job_id in self.server.manager.jobs
            if not saved and directory.resolve().parent == self.server.manager.directory.resolve():
                shutil.rmtree(directory, ignore_errors=True)
            self.close_connection = True
            with contextlib.suppress(OSError):
                self._reply(400, {"error": str(exc)})
        finally:
            self.server.upload_lock.release()

    def do_DELETE(self):
        if not self._allowed(mutate=True):
            return
        match = re.fullmatch(r"/api/jobs/([a-f0-9]{32})", urlsplit(self.path).path)
        if not match:
            return self._reply(404, {"error": "操作不存在"})
        try:
            self.server.manager.delete(match[1])
            self._reply(200, {"deleted": True})
        except KeyError:
            self._reply(404, {"error": "任务不存在"})
        except (ValueError, OSError) as exc:
            self._reply(409, {"error": str(exc)})


@contextlib.contextmanager
def instance_lock(path: Path):
    with path.open("a+b") as file:
        file.seek(0, os.SEEK_END)
        if file.tell() == 0:
            file.write(b"0")
            file.flush()
        file.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            file.seek(0)
            if os.name == "nt":
                msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(file, fcntl.LOCK_UN)


def existing_server(root: Path):
    info = read_json(root / "data/server.json", {})
    try:
        port = int(info["port"])
        if not 1 <= port <= 65535:
            return None
        url = f"http://127.0.0.1:{port}"
        with urlopen(url + "/api/config", timeout=2) as response:
            data = json.load(response)
        if not secrets.compare_digest(data["token"], info["token"]):
            return None
        return url, info
    except (OSError, ValueError, KeyError):
        return None


def main(argv=None):
    parser = argparse.ArgumentParser(description="RallyCut local application")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--open", action="store_true")
    parser.add_argument("--stop", action="store_true")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    configure_environment(root)
    existing = existing_server(root)
    if existing:
        url, info = existing
        if args.stop:
            request = Request(url + "/api/shutdown", data=b"", method="POST",
                              headers={"X-RallyCut-Token": info["token"]})
            with urlopen(request, timeout=30):
                pass
            print("RallyCut stopped.")
        else:
            if args.open:
                webbrowser.open(url)
            print(url, flush=True)
        return 0
    if args.stop:
        print("RallyCut is not running.")
        return 0
    try:
        with instance_lock(root / "data/server.lock"):
            manager = JobManager(root)
            server = None
            try:
                for port in ([args.port] if args.port == 0 else [args.port, 0]):
                    try:
                        server = AppServer(("127.0.0.1", port), root, manager)
                        break
                    except OSError:
                        continue
                if server is None:
                    raise RuntimeError("无法打开本机服务端口。")
                url = f"http://127.0.0.1:{server.server_port}"
                atomic_json(root / "data/server.json", {
                    "pid": os.getpid(), "port": server.server_port, "token": server.token,
                })
                print(f"RallyCut {VERSION}: {url}", flush=True)
                print("Local processing: CUDA preferred, CPU fallback. Close with Stop.cmd or Ctrl+C.", flush=True)
                if args.open:
                    webbrowser.open(url)
                server.serve_forever(poll_interval=0.3)
            except KeyboardInterrupt:
                pass
            finally:
                manager.close()
                if server:
                    server.server_close()
                info = read_json(root / "data/server.json", {})
                if info.get("pid") == os.getpid():
                    (root / "data/server.json").unlink(missing_ok=True)
        return 0
    except OSError as exc:
        print(f"Cannot start RallyCut: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
