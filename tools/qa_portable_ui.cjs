// Maintainer-only acceptance check. Not included in the user distribution.
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const { chromium } = require("playwright");

(async () => {
  const packageRoot = process.argv[2];
  const qaRoot = process.argv[3];
  const videoPath = process.env.RALLYCUT_QA_VIDEO;
  const referencePath = process.env.RALLYCUT_QA_REFERENCE;
  if (!packageRoot || !qaRoot || !videoPath || !referencePath)
    throw new Error("Usage: node tools/qa_portable_ui.cjs <isolated package root> <output>. Set RALLYCUT_QA_VIDEO to the known demo_forrating2 fixture and RALLYCUT_QA_REFERENCE to its smoke_verification.json. Use a disposable test package.");
  fs.mkdirSync(qaRoot, { recursive: true });
  const { port } = JSON.parse(fs.readFileSync(path.join(packageRoot, "data/server.json"), "utf8"));
  const base = `http://127.0.0.1:${port}`;
  const browser = await chromium.launch({
    channel: process.env.RALLYCUT_BROWSER_CHANNEL || (process.platform === "win32" ? "msedge" : undefined),
    headless: true,
    downloadsPath: path.resolve(qaRoot),
  });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1050 }, acceptDownloads: true });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  const outside = [];
  page.on("request", request => {
    if (!request.url().startsWith(base) && !request.url().startsWith("blob:"))
      outside.push(request.url());
  });
  try {
    await page.goto(base);
    await page.waitForFunction(() => document.querySelector("#connectionLabel").textContent.includes("本机运行"));
    if (process.argv.includes("--reuse")) {
      await page.locator(".job-item").first().click();
    } else {
      await page.screenshot({ path: path.join(qaRoot, "welcome.png"), fullPage: true });
      await page.locator("#videoInput").setInputFiles(videoPath);
      await page.waitForFunction(() => !document.querySelector("#processingCard").hidden);
      await page.screenshot({ path: path.join(qaRoot, "processing.png"), fullPage: true });
      console.log("Real upload accepted; waiting for embedded worker.");
    }
    await page.waitForFunction(() => !document.querySelector("#resultView").hidden ||
      !document.querySelector("#failedCard").hidden, null, { timeout: 240000 });
    if (await page.locator("#failedCard").isVisible())
      throw new Error("Packaged worker failed: " + await page.locator("#failedMessage").innerText());
    await page.waitForFunction(() => document.querySelector("#video").readyState >= 2);
    const jobs = await (await context.request.get(base + "/api/jobs")).json();
    const completed = jobs.jobs.find(job => job.state === "completed");
    if (!completed) throw new Error("No completed job");
    const result = await (await context.request.get(base + `/api/jobs/${completed.id}/result`)).json();
    if (result.rallies.length !== 3) throw new Error("Expected known 960 reference's 3 intervals");
    const reference = JSON.parse(fs.readFileSync(
      referencePath, "utf8"));
    const actualIntervals = result.rallies.map(rally => [rally.start_seconds, rally.end_seconds]);
    const maxBoundaryDifference = Math.max(...actualIntervals.flatMap((row,i)=>row.map((value,j)=>Math.abs(value-reference.intervals[i][j]))));
    if (maxBoundaryDifference > 0.001)
      throw new Error("Packaged inference changed the reference interval endpoints");
    if (process.argv.includes("--expect-gpu")) {
      if (result.model.device !== "GPU (NVIDIA CUDA)" || !result.model.sessions.some(s=>s.gpu_runs>0))
        throw new Error("Expected actual CUDA inference");
    } else if (result.model.sessions.some(s => JSON.stringify(s.providers) !== '["CPUExecutionProvider"]')) {
      throw new Error("Expected CPU fallback");
    }
    const deviceText = await page.locator("#deviceSummary").innerText();
    if (!deviceText.includes(result.model.device)) throw new Error("UI device does not match actual runtime");
    await page.locator(".rally-seek").first().click();
    await page.waitForTimeout(700);
    const playback = await page.locator("#video").evaluate(v => ({ time: v.currentTime, paused: v.paused, ready: v.readyState }));
    if (playback.paused || playback.time <= result.rallies[0].start_seconds) throw new Error("Video did not play");
    await page.locator("#video").evaluate(v => { v.pause(); v.currentTime = 12; });
    await page.waitForFunction(() => Math.abs(document.querySelector("#video").currentTime - 12) < .1);
    await page.waitForTimeout(300);
    const pixels = await page.locator("#poseCanvas").evaluate(canvas => {
      const values = canvas.getContext("2d").getImageData(0, 0, canvas.width, canvas.height).data;
      let count = 0; for (let i = 3; i < values.length; i += 4) if (values[i]) count++;
      return count;
    });
    if (pixels === 0) throw new Error("No actual skeleton rendered at 12 seconds");
    await page.locator("#nextSample").click();
    const stepped = await page.locator("#video").evaluate(v => v.currentTime);
    if (stepped <= 12 || stepped > 12.5) throw new Error("Sample stepping failed");
    await page.locator("#showPose").uncheck();
    await page.locator("#showPose").check();
    await page.locator("#timeWindow").selectOption("0");
    await page.screenshot({ path: path.join(qaRoot, "result-desktop.png"), fullPage: true });
    const [download] = await Promise.all([
      page.waitForEvent("download"),
      page.locator(".rally-download").first().click(),
    ]);
    await download.saveAs(path.join(qaRoot, "downloaded-rally-001.mp4"));
    if (await download.failure()) throw new Error("Clip download failed");
    const downloadChecks = [];
    for (const [selector, filename] of [["#downloadJson", "result.json"], ["#downloadAll", "clips.zip"]]) {
      const [artifact] = await Promise.all([page.waitForEvent("download"), page.locator(selector).click()]);
      const destination = path.join(qaRoot, "downloaded-" + filename);
      await artifact.saveAs(destination);
      if (await artifact.failure()) throw new Error(filename + " download failed");
      const hash = file => crypto.createHash("sha256").update(fs.readFileSync(file)).digest("hex");
      if (hash(destination) !== hash(path.join(packageRoot, "data/jobs", completed.id, filename)))
        throw new Error(filename + " download changed content");
      downloadChecks.push({ file: filename, bytes: fs.statSync(destination).size, sha256: hash(destination) });
    }
    const range = await context.request.get(base + `/api/jobs/${completed.id}/media`, { headers: { Range: "bytes=0-255" } });
    if (range.status() !== 206 || (await range.body()).length !== 256) throw new Error("Video Range request failed");
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({ path: path.join(qaRoot, "result-mobile.png"), fullPage: true });
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth);
    if (overflow) throw new Error("Mobile horizontal overflow");
    await page.setViewportSize({ width: 1440, height: 1050 });
    await page.reload();
    await page.locator(".job-item").first().click();
    await page.locator("#resultView").waitFor({ state: "visible" });
    console.log("Playback, skeleton, timeline, download, mobile, and history passed.");

    // Start and cancel a real worker, then verify the interface remains usable.
    await page.locator("#videoInput").setInputFiles(videoPath);
    await page.locator("#cancelJob").waitFor({ state: "visible" });
    await page.waitForTimeout(1600);
    await page.locator("#cancelJob").click();
    await page.waitForFunction(() => document.querySelector("#failedTitle").textContent.includes("已取消"));
    await page.waitForTimeout(500);
    page.once("dialog", dialog => dialog.accept());
    await page.locator("#deleteJob").click();
    await page.waitForFunction(() => document.querySelectorAll(".job-item").length === 1);

    await page.locator("#videoInput").setInputFiles({
      name: "损坏的样本.mp4", mimeType: "video/mp4", buffer: Buffer.from("not a video"),
    });
    await page.locator("#failedCard").waitFor({ state: "visible", timeout: 30000 });
    const failureMessage = await page.locator("#failedMessage").innerText();
    if (!failureMessage.includes("读取")) throw new Error("Invalid video was not clearly rejected: " + failureMessage);
    page.once("dialog", dialog => dialog.accept());
    await page.locator("#deleteJob").click();
    await page.waitForFunction(() => document.querySelectorAll(".job-item").length === 1);
    await page.locator(".job-item").first().click();
    await page.locator("#resultView").waitFor({ state: "visible" });
    if (errors.length) throw new Error("Browser errors: " + errors.join("; "));
    if (outside.length) throw new Error("Unexpected external requests: " + outside.join("; "));
    const evidence = {
      packageRoot, job_id: completed.id, browser_errors: errors, external_requests: outside,
      model_sessions: result.model.sessions, interval_count: result.rallies.length,
      analysis_seconds: result.analysis_seconds, total_seconds: result.total_seconds,
      exact_reference_interval_parity: JSON.stringify(actualIntervals) === JSON.stringify(reference.intervals),
      max_boundary_difference_seconds: maxBoundaryDifference,
      inference_device: result.model.device,
      fallback_reason: result.model.fallback_reason,
      displayed_device: deviceText,
      skeleton_pixels: pixels, stepped_seconds: stepped, mobile_overflow: overflow,
      invalid_video_message: failureMessage, cancelled_real_worker: true,
      downloads: downloadChecks,
      download_bytes: fs.statSync(path.join(qaRoot, "downloaded-rally-001.mp4")).size,
    };
    fs.writeFileSync(path.join(qaRoot, "acceptance.json"), JSON.stringify(evidence, null, 2));
    console.log(JSON.stringify(evidence));
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error.stack); process.exit(1); });
