/* Local-only interface. The backend owns analysis, timestamps, and saved results. */
"use strict";
const $ = (id) => document.getElementById(id);
const state = {config:null,jobs:[],selected:null,result:null,resultId:null,loadingResult:null,upload:null,polling:false,connected:false,toastTimer:null,drawTime:-1,plotRange:[0,30],hoverTime:null};
const labels = {queued:"等待分析",running:"分析中",completed:"已完成",failed:"未完成",cancelled:"已取消"};
const phases = {queued:"等待分析",preparing:"准备视频",loading:"载入模型",analyzing:"识别回合",inference:"识别回合",pose:"提取画面特征",decoding:"整理回合",exporting:"导出回合",saving:"保存结果",completed:"分析完成",cancelled:"已取消"};
const skeletonEdges = [[0,1],[0,2],[1,3],[2,4],[5,6],[5,7],[7,9],[6,8],[8,10],[5,11],[6,12],[11,12],[11,13],[13,15],[12,14],[14,16]];
const video = $("video");
function seconds(value) { const v=Number(value);return Number.isFinite(v)?Math.max(0,v):0; }
function formatTime(value,decimal=false) { const ticks=Math.round(seconds(value)*10),s=decimal?Math.floor(ticks/10):Math.floor(seconds(value)),h=Math.floor(s/3600),m=Math.floor((s%3600)/60),r=s%60;return (h?String(h).padStart(2,"0")+":":"")+String(m).padStart(2,"0")+":"+String(r).padStart(2,"0")+(decimal?"."+(ticks%10):""); }
function formatDuration(value) { const s=Math.round(seconds(value));if(s<60)return s+" 秒";if(s<3600)return Math.floor(s/60)+" 分 "+(s%60)+" 秒";return Math.floor(s/3600)+" 时 "+Math.floor(s%3600/60)+" 分"; }
function toast(message) { $("toast").textContent=message;$("toast").hidden=false;clearTimeout(state.toastTimer);state.toastTimer=setTimeout(()=>{$("toast").hidden=true;},4200); }
function jobURL(id,suffix="") { return "/api/jobs/"+encodeURIComponent(id)+suffix; }
async function api(path,options={}) {
  const response=await fetch(path,{cache:"no-store",...options,headers:{...(options.method&&options.method!=="GET"?{"X-RallyCut-Token":state.config?.token||""}:{}),...(options.headers||{})}});
  if(!response.ok){let message="请求未成功（"+response.status+"）";try{const data=await response.json();const detail=data.error||data.detail||data.message;if(typeof detail==="string")message=detail;else if(detail)message=JSON.stringify(detail);}catch{}throw new Error(message);}
  if(response.status===204)return null;return response.json();
}
function setConnection(connected) { state.connected=connected;$("connectionDot").className="status-dot "+(connected?"connected":"disconnected");$("connectionLabel").textContent=connected?"本机运行 · 离线可用":"正在重新连接";$("connectionError").hidden=connected; }
async function initialize() {
  try { state.config=await api("/api/config");$("versionLabel").textContent=state.config.version?"v"+state.config.version:"";const max=Number(state.config.max_upload_bytes);if(max>0)$("formatHint").textContent="MP4 / MOV / MKV / AVI / WebM · 最大 "+(max/1024**3).toFixed(max%1024**3?1:0)+" GB";await poll(); }
  catch {setConnection(false);}
}
function showWelcome() { state.selected=null;state.result=null;state.resultId=null;video.pause();video.removeAttribute("src");video.load();$("welcomeView").hidden=false;$("jobView").hidden=true;$("uploadError").hidden=true;renderJobs(); }
function dateLabel(value) {if(!value)return "";const d=new Date(typeof value==="number"&&value<1e12?value*1000:value);return Number.isNaN(d.getTime())?"":d.toLocaleDateString("zh-CN",{month:"2-digit",day:"2-digit"})+" "+d.toLocaleTimeString("zh-CN",{hour:"2-digit",minute:"2-digit"});}
function renderJobs() {
  $("jobCount").textContent=String(state.jobs.length);$("historyEmpty").hidden=state.jobs.length>0;const fragment=document.createDocumentFragment();
  for(const job of state.jobs) {
    const button=document.createElement("button");button.type="button";button.className="job-item"+(state.selected===job.id?" selected":"");button.title=job.filename||"未命名视频";
    const icon=document.createElement("span");icon.className="job-icon";icon.textContent="▷";icon.setAttribute("aria-hidden","true");
    const info=document.createElement("div");info.className="job-info";const title=document.createElement("strong");title.textContent=job.filename||"未命名视频";const meta=document.createElement("div");meta.className="job-meta";const dot=document.createElement("i");dot.className=job.state;const status=document.createElement("span");status.textContent=(labels[job.state]||job.state)+(job.state==="running"?" "+Math.floor(seconds(job.progress)*100)+"%":"");const date=document.createElement("span");date.textContent=dateLabel(job.created_at);meta.append(dot,status,date);info.append(title,meta);button.append(icon,info);button.addEventListener("click",()=>selectJob(job.id));fragment.append(button);
  }
  $("jobList").replaceChildren(fragment);
}
function selectJob(id) {
  if(state.selected!==id){state.result=null;state.resultId=null;video.pause();video.removeAttribute("src");video.load();$("mediaError").hidden=true;}
  state.selected=id;$("welcomeView").hidden=true;$("jobView").hidden=false;renderJobs();renderSelected();window.scrollTo({top:0,behavior:"smooth"});
}
async function poll() {
  if(state.polling)return;state.polling=true;
  try {
    if(!state.config){state.config=await api("/api/config");$("versionLabel").textContent=state.config.version?"v"+state.config.version:"";}
    const data=await api("/api/jobs");state.jobs=Array.isArray(data.jobs)?data.jobs:[];
    state.jobs.sort((a,b)=>new Date(b.created_at)-new Date(a.created_at));setConnection(true);renderJobs();
    if(state.selected&&!state.jobs.some(j=>j.id===state.selected))showWelcome();
    else if(state.selected)await renderSelected();
  } catch {setConnection(false);}
  finally{state.polling=false;}
}
async function renderSelected() {
  const job=state.jobs.find(j=>j.id===state.selected);if(!job)return;
  $("jobTitle").textContent=job.filename||"未命名视频";$("jobSubtitle").textContent=[dateLabel(job.created_at),labels[job.state]||job.state].filter(Boolean).join(" · ");
  const active=job.state==="queued"||job.state==="running",failed=job.state==="failed"||job.state==="cancelled";
  $("processingCard").hidden=!active;$("failedCard").hidden=!failed;$("resultView").hidden=job.state!=="completed"||state.resultId!==job.id;
  $("deleteJob").hidden=active;
  if(active) {
    $("processingNote").textContent=job.device ? "计算设备："+job.device+(job.device_message?" · "+job.device_message:"") : "自动选择计算设备，请保持启动窗口开启。";
    const p=Math.max(0,Math.min(1,Number(job.progress)||0));$("phaseLabel").textContent=phases[job.phase]||(job.state==="queued"?"等待分析":"正在分析");$("processingTitle").textContent=job.state==="queued"?"视频已就位，等待轮到它。":"让每个回合，各归其位。";$("processingMessage").textContent=job.message||(job.state==="queued"?"前一个视频完成后，会自动开始。":"正在读取画面并识别回合…");$("processingPercent").replaceChildren(document.createTextNode(String(Math.floor(p*100))),Object.assign(document.createElement("small"),{textContent:"%"}));$("processingBar").value=p;$("elapsedLabel").textContent=job.elapsed_seconds?"已用时 "+formatDuration(job.elapsed_seconds):"";$("cancelJob").disabled=false;
  } else if(failed) {$("failedTitle").textContent=job.state==="cancelled"?"这次分析已取消":"本次分析未完成";$("failedMessage").textContent=job.error||job.message||(job.state==="cancelled"?"可以重新选择视频，开始下一次分析。":"请重新选择视频后再试。");}
  else if(job.state==="completed"&&state.resultId!==job.id&&state.loadingResult!==job.id) {
    state.loadingResult=job.id;
    try {const result=await api(jobURL(job.id,"/result"));if(state.selected===job.id){state.result=result;state.resultId=job.id;renderResult(job,result);}}
    catch(error){if(state.selected===job.id){$("failedCard").hidden=false;$("failedTitle").textContent="暂时无法读取结果";$("failedMessage").textContent=error.message;}}
    finally{if(state.loadingResult===job.id)state.loadingResult=null;}
  }
}
function chooseFile() {if(state.upload){toast("当前视频正在导入，请稍候或先取消导入。");return;}showWelcome();$("videoInput").click();}
function uploadFile(file) {
  if(!file||state.upload)return;
  showWelcome();
  if(!state.config||!state.connected){$("uploadError").textContent="本机服务尚未连接，请稍后再试。";$("uploadError").hidden=false;return;}
  if(!/\.(mp4|mov|mkv|avi|webm|m4v|mts|m2ts|ts)$/i.test(file.name)){showUploadError("请选择 MP4、MOV、MKV、AVI、WebM、M4V、MTS、M2TS 或 TS 格式的视频。");return;}
  if(file.size===0){showUploadError("这个文件是空的，请选择其他视频。");return;}
  if(state.config.max_upload_bytes&&file.size>state.config.max_upload_bytes){showUploadError("视频超过当前允许的文件大小，请先缩短视频或降低码率。");return;}
  $("uploadError").hidden=true;$("uploadProgress").hidden=false;$("uploadName").textContent=file.name;$("uploadPercent").textContent="0%";$("uploadBar").value=0;$("uploadHint").textContent="正在复制到本地工作目录…";$("dropZone").classList.add("busy");
  const request=new XMLHttpRequest();state.upload=request;request.open("POST","/api/jobs");request.setRequestHeader("Content-Type","application/octet-stream");request.setRequestHeader("X-RallyCut-Token",state.config.token);request.setRequestHeader("X-File-Name",encodeURIComponent(file.name));
  request.upload.onprogress=(e)=>{if(e.lengthComputable){const pct=Math.floor(e.loaded/e.total*100);$("uploadPercent").textContent=pct+"%";$("uploadBar").value=pct;if(pct===100)$("uploadHint").textContent="导入完成，正在创建分析任务…";}};
  request.onload=async()=>{finishUpload();let data;try{data=JSON.parse(request.responseText);}catch{}if(request.status>=200&&request.status<300&&data?.id){$("uploadProgress").hidden=true;state.jobs.unshift(data);selectJob(data.id);await poll();}else showUploadError(typeof data?.error==="string"?data.error:typeof data?.detail==="string"?data.detail:"导入未成功，请重试。（"+request.status+"）");};
  request.onerror=()=>{finishUpload();showUploadError("连接中断，视频未导入。请确认启动窗口仍然开启。");};request.onabort=()=>{finishUpload();$("uploadProgress").hidden=true;toast("已取消导入");};request.send(file);
}
function finishUpload(){state.upload=null;$("dropZone").classList.remove("busy");$("videoInput").value="";}
function showUploadError(message){$("uploadError").textContent=message;$("uploadError").hidden=false;$("uploadProgress").hidden=true;}
async function cancelJob(){if(!state.selected)return;$("cancelJob").disabled=true;try{await api(jobURL(state.selected,"/cancel"),{method:"POST"});toast("已请求取消，正在停止当前任务");await poll();}catch(e){toast(e.message);$("cancelJob").disabled=false;}}
async function deleteJob(){const job=state.jobs.find(j=>j.id===state.selected);if(!job)return;if(!confirm("删除“"+job.filename+"”的本地记录、导入副本和分析结果？原始视频不会被删除。"))return;try{await api(jobURL(job.id),{method:"DELETE"});showWelcome();await poll();toast("记录已删除");}catch(e){toast(e.message);}}
function renderResult(job,result) {
  $("deviceSummary").textContent="本次识别使用："+(result.model?.device||"CPU")+(result.model?.fallback_reason?" · "+result.model.fallback_reason:"")+" · 视频导出使用 CPU";
  result.rallies=Array.isArray(result.rallies)?result.rallies:[];result.poses=Array.isArray(result.poses)?result.poses:[];result.scores=result.scores||{timestamps:[],pointness:[],start:[],end:[]};
  $("resultView").hidden=false;$("failedCard").hidden=true;$("durationMetric").textContent=formatTime(result.duration_seconds);$("rallyMetric").textContent=String(result.rallies.length);$("activeMetric").textContent=formatTime(result.rallies.reduce((sum,r)=>sum+seconds(r.duration_seconds??r.end_seconds-r.start_seconds),0));$("analysisMetric").textContent=formatDuration(result.analysis_seconds);$("rallyCountBadge").textContent=String(result.rallies.length);
  $("downloadJson").href=jobURL(job.id,"/download");$("downloadClips").href=$("downloadAll").href=jobURL(job.id,"/clips.zip");$("downloadClips").hidden=$("downloadAll").hidden=result.rallies.length===0;
  const fragment=document.createDocumentFragment();for(const [index,rally] of result.rallies.entries()) {
    const row=document.createElement("div");row.className="rally-row";row.dataset.index=String(index);
    const seekButton=document.createElement("button");seekButton.type="button";seekButton.className="rally-seek";const strong=document.createElement("strong");strong.textContent="回合 "+String(index+1).padStart(2,"0");const range=document.createElement("span");range.textContent=formatTime(rally.start_seconds,true)+" — "+formatTime(rally.end_seconds,true);seekButton.append(strong,range);seekButton.addEventListener("click",()=>{seek(rally.start_seconds);video.play().catch(()=>{});});
    const duration=document.createElement("span");duration.className="rally-duration";duration.textContent=seconds(rally.duration_seconds??rally.end_seconds-rally.start_seconds).toFixed(1)+"s";const download=document.createElement("a");download.className="rally-download";download.href=jobURL(job.id,"/clips/"+String(rally.id??index+1).padStart(3,"0")+".mp4");download.textContent="↓";download.title="下载回合 "+(index+1);download.setAttribute("aria-label",download.title);download.setAttribute("download","");download.addEventListener("click",()=>toast("正在准备回合片段，完成后浏览器会开始下载"));row.append(seekButton,duration,download);fragment.append(row);
  }
  $("rallyList").replaceChildren(fragment);$("noRallies").hidden=result.rallies.length>0;video.src=jobURL(job.id,"/media");video.playbackRate=Number($("playbackSpeed").value);video.load();state.drawTime=-1;state.hoverTime=null;
  for(const id of ["scoreCanvas","overviewCanvas"])$(id).setAttribute("aria-valuemax",String(seconds(result.duration_seconds)));
  requestAnimationFrame(()=>draw(true));
}
function nearestIndex(array,value,getter=(v)=>v) {if(!array.length)return -1;let low=0,high=array.length-1;while(low<high){const mid=Math.floor((low+high)/2);if(getter(array[mid])<value)low=mid+1;else high=mid;}return low>0&&Math.abs(getter(array[low-1])-value)<Math.abs(getter(array[low])-value)?low-1:low;}
function poseAt(time) {const poses=state.result?.poses||[],index=nearestIndex(poses,time,p=>Number(p.timestamp_seconds));return index>=0&&Math.abs(Number(poses[index].timestamp_seconds)-time)<=.45?poses[index]:null;}
function seek(time) {if(!state.result)return;video.currentTime=Math.min(seconds(state.result.duration_seconds),seconds(time));draw(true);}
function stepSample(direction) {video.pause();const poses=state.result?.poses||[];const timestamps=poses.length?poses.map(p=>p.timestamp_seconds):(state.result?.scores?.timestamps||[]);if(!timestamps.length)return;let index=nearestIndex(timestamps,video.currentTime);if(direction>0&&timestamps[index]<=video.currentTime+.015)index++;if(direction<0&&timestamps[index]>=video.currentTime-.015)index--;index=Math.max(0,Math.min(timestamps.length-1,index));seek(timestamps[index]);}
function prepareCanvas(canvas) {const rect=canvas.getBoundingClientRect(),dpr=window.devicePixelRatio||1,w=Math.max(1,rect.width),h=Math.max(1,rect.height);if(canvas.width!==Math.round(w*dpr)||canvas.height!==Math.round(h*dpr)){canvas.width=Math.round(w*dpr);canvas.height=Math.round(h*dpr);}const ctx=canvas.getContext("2d");ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,w,h);return {ctx,w,h};}
function drawPose(time) {
  const {ctx,w,h}=prepareCanvas($("poseCanvas")),sample=poseAt(time);$("sampleLabel").textContent=sample?"采样 "+formatTime(sample.timestamp_seconds,true):"此处无采样";
  const present=[];if(sample?.near)present.push("近端");if(sample?.far)present.push("远端");$("poseStatus").textContent=present.length?"当前检测："+present.join("、"):"当前未检测到人体骨架";
  if(!$("showPose").checked||!sample)return;
  const rw=Number(state.result.pose_reference_size?.[0])||1280,rh=Number(state.result.pose_reference_size?.[1])||720;const vw=video.videoWidth||state.result.video?.width||rw,vh=video.videoHeight||state.result.video?.height||rh,scale=Math.min(w/vw,h/vh),displayW=vw*scale,displayH=vh*scale,ox=(w-displayW)/2,oy=(h-displayH)/2;
  for(const [key,color] of [["near","#c4f12c"],["far","#6acbff"]]) {
    const person=sample[key];if(!person||!Array.isArray(person.keypoints))continue;
    const points=person.keypoints.map(p=>Array.isArray(p)?p:[p.x,p.y,p.confidence??p.score??0]);const valid=(i)=>points[i]&&Number.isFinite(points[i][0])&&Number.isFinite(points[i][1])&&points[i][2]>=.35;
    const xy=(i)=>[ox+points[i][0]/rw*displayW,oy+points[i][1]/rh*displayH];ctx.lineCap="round";ctx.lineJoin="round";ctx.lineWidth=Math.max(1.4,w/340);ctx.strokeStyle=color;ctx.shadowColor="#000b";ctx.shadowBlur=3;
    for(const [a,b] of skeletonEdges){if(!valid(a)||!valid(b))continue;const p=xy(a),q=xy(b);ctx.beginPath();ctx.moveTo(...p);ctx.lineTo(...q);ctx.stroke();}
    ctx.fillStyle=color;for(let i=0;i<points.length;i++){if(!valid(i))continue;const p=xy(i);ctx.beginPath();ctx.arc(...p,Math.max(2,w/240),0,Math.PI*2);ctx.fill();}ctx.shadowBlur=0;
  }
}
function activeRally(time) {const rallies=state.result?.rallies||[];return rallies.findIndex(r=>time>=Number(r.start_seconds)&&time<=Number(r.end_seconds));}
function draw(force=false) {
  if(!state.result||$("resultView").hidden)return;const time=seconds(video.currentTime);
  if(!force&&Math.abs(time-state.drawTime)<.035)return;state.drawTime=time;
  drawPose(time);drawScores(time);drawOverview(time);$("currentTime").textContent=formatTime(time,true);const active=activeRally(time);$("videoStatus").textContent=active>=0?"回合 "+String(active+1).padStart(2,"0")+" · 进行中":"回合间隙";$("videoStatus").classList.toggle("active",active>=0);
  document.querySelectorAll(".rally-row").forEach((row,index)=>row.classList.toggle("active",index===active));for(const id of ["scoreCanvas","overviewCanvas"])$(id).setAttribute("aria-valuenow",time.toFixed(1));
}
function viewRange(time) {const duration=seconds(state.result.duration_seconds)||1,windowLength=Number($("timeWindow").value);if(!windowLength||duration<=windowLength)return [0,duration];const left=Math.max(0,Math.min(duration-windowLength,time-windowLength*.36));return [left,left+windowLength];}
function drawScores(time) {
  const {ctx,w,h}=prepareCanvas($("scoreCanvas")),[left,right]=viewRange(time);state.plotRange=[left,right];
  const margin=w<500?49:65,end=18,plotW=w-margin-end,range=right-left||1,px=(t)=>margin+(t-left)/range*plotW;ctx.font=(w<500?"9":"10")+"px Segoe UI, Microsoft YaHei, sans-serif";
  const laneTop=12,laneH=19,rowTop=52,rowH=48,gap=14,bottom=rowTop+3*(rowH+gap)-gap;ctx.fillStyle="#f6f0fb";ctx.fillRect(margin,laneTop,plotW,laneH);ctx.fillStyle="#a18aaf";ctx.fillText("回合",12,laneTop+13);
  for(const rally of state.result.rallies){const a=Math.max(left,seconds(rally.start_seconds)),b=Math.min(right,seconds(rally.end_seconds));if(b<a)continue;ctx.fillStyle="#8b42eeb5";ctx.fillRect(px(a),laneTop,Math.max(1,px(b)-px(a)),laneH);if(px(b)-px(a)>29){ctx.fillStyle="#fff";ctx.font="8px Segoe UI";ctx.fillText(String(rally.id),px(a)+5,laneTop+12);}}
  const ticks=4;for(let i=0;i<=ticks;i++){const t=left+range*i/ticks,x=px(t);ctx.strokeStyle="#f0eaf5";ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(x,rowTop-3);ctx.lineTo(x,bottom);ctx.stroke();ctx.fillStyle="#ac9bb8";ctx.textAlign=i===0?"left":i===ticks?"right":"center";ctx.font="8px Segoe UI";ctx.fillText(formatTime(t),x,h-8);}ctx.textAlign="left";
  const scores=state.result.scores,timestamps=Array.isArray(scores.timestamps)?scores.timestamps:[],currentIndex=nearestIndex(timestamps,time),tracks=[["pointness","回合内","#8b42ee"],["start","开始","#289ec7"],["end","结束","#e48a59"]];
  tracks.forEach(([name,label,color],trackIndex)=>{
    const top=rowTop+trackIndex*(rowH+gap),values=scores[name]||[];ctx.fillStyle="#9e87ad";ctx.font="9px Microsoft YaHei, sans-serif";ctx.fillText(label,12,top+18);const current=Number(values[currentIndex]);ctx.font="9px Segoe UI";ctx.fillStyle=color;ctx.fillText(Number.isFinite(current)?current.toFixed(2):"—",12,top+33);
    ctx.strokeStyle="#e9dfef";ctx.setLineDash([3,4]);ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(margin,top+rowH*.5);ctx.lineTo(w-end,top+rowH*.5);ctx.stroke();ctx.setLineDash([]);
    ctx.save();ctx.beginPath();ctx.rect(margin,top,plotW,rowH);ctx.clip();ctx.beginPath();let started=false;for(let i=0;i<timestamps.length;i++){if(timestamps[i]<left-.5||timestamps[i]>right+.5)continue;const value=Number(values[i]);if(!Number.isFinite(value)){started=false;continue;}const x=px(timestamps[i]),y=top+rowH*(1-Math.min(1,Math.max(0,value)));if(!started){ctx.moveTo(x,y);started=true;}else ctx.lineTo(x,y);}ctx.strokeStyle=color;ctx.lineWidth=1.6;ctx.stroke();ctx.restore();
    if(currentIndex>=0&&Number.isFinite(current)&&timestamps[currentIndex]>=left&&timestamps[currentIndex]<=right){ctx.beginPath();ctx.arc(px(timestamps[currentIndex]),top+rowH*(1-Math.max(0,Math.min(1,current))),2.8,0,Math.PI*2);ctx.fillStyle=color;ctx.fill();}
  });
  ctx.strokeStyle="#3b214f";ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(px(time),7);ctx.lineTo(px(time),bottom+3);ctx.stroke();ctx.fillStyle="#3b214f";ctx.beginPath();ctx.moveTo(px(time)-3,4);ctx.lineTo(px(time)+3,4);ctx.lineTo(px(time),9);ctx.fill();
  if(state.hoverTime!==null&&state.hoverTime>=left&&state.hoverTime<=right){const x=px(state.hoverTime);ctx.strokeStyle="#b6a0c5";ctx.setLineDash([2,4]);ctx.beginPath();ctx.moveTo(x,10);ctx.lineTo(x,bottom);ctx.stroke();ctx.setLineDash([]);const text=formatTime(state.hoverTime,true),tw=ctx.measureText(text).width+12,tx=Math.min(w-tw-5,Math.max(5,x-tw/2));ctx.fillStyle="#f3e9fb";ctx.fillRect(tx,bottom+1,tw,15);ctx.fillStyle="#805299";ctx.font="8px Segoe UI";ctx.fillText(text,tx+6,bottom+11);}
}
function drawOverview(time) {const {ctx,w,h}=prepareCanvas($("overviewCanvas")),pad=w<500?16:22,duration=seconds(state.result.duration_seconds)||1,width=w-pad*2,px=t=>pad+t/duration*width;ctx.fillStyle="#f2ebf7";ctx.fillRect(pad,12,width,18);for(const rally of state.result.rallies){ctx.fillStyle="#ad7edc";ctx.fillRect(px(rally.start_seconds),12,Math.max(1,(rally.end_seconds-rally.start_seconds)/duration*width),18);}const [a,b]=state.plotRange;ctx.strokeStyle="#765190";ctx.lineWidth=1;ctx.strokeRect(px(a),10,Math.max(1,px(b)-px(a)),22);ctx.strokeStyle="#281834";ctx.lineWidth=2;ctx.beginPath();ctx.moveTo(px(time),7);ctx.lineTo(px(time),35);ctx.stroke();ctx.font="8px Segoe UI";ctx.fillStyle="#ab9bb6";ctx.textAlign="left";ctx.fillText("00:00",pad,h-7);ctx.textAlign="right";ctx.fillText(formatTime(duration),w-pad,h-7);ctx.textAlign="left";}
function canvasTime(event,overview=false) {const canvas=overview?$("overviewCanvas"):$("scoreCanvas"),rect=canvas.getBoundingClientRect(),x=event.clientX-rect.left,pad=overview?(rect.width<500?16:22):(rect.width<500?49:65),end=overview?pad:18,[a,b]=overview?[0,seconds(state.result?.duration_seconds)]:state.plotRange;return a+Math.max(0,Math.min(1,(x-pad)/(rect.width-pad-end)))*(b-a);}
for(const id of ["topUpload","newVideo","addVideo","retryUpload"])$(id).addEventListener("click",chooseFile);
$("dropZone").addEventListener("click",chooseFile);$("dropZone").addEventListener("keydown",(e)=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();chooseFile();}});
$("videoInput").addEventListener("change",(e)=>uploadFile(e.target.files[0]));$("cancelUpload").addEventListener("click",()=>state.upload?.abort());$("cancelJob").addEventListener("click",cancelJob);$("deleteJob").addEventListener("click",deleteJob);
for(const event of ["dragenter","dragover"])$("dropZone").addEventListener(event,(e)=>{e.preventDefault();$("dropZone").classList.add("dragging");});
for(const event of ["dragleave","drop"])$("dropZone").addEventListener(event,(e)=>{e.preventDefault();$("dropZone").classList.remove("dragging");});
$("dropZone").addEventListener("drop",(e)=>{const files=e.dataTransfer.files;if(files.length>1)toast("每次导入一个视频；完成导入后可以继续添加。");uploadFile(files[0]);});
window.addEventListener("dragover",(e)=>e.preventDefault());window.addEventListener("drop",(e)=>e.preventDefault());
$("previousSample").addEventListener("click",()=>stepSample(-1));$("nextSample").addEventListener("click",()=>stepSample(1));$("showPose").addEventListener("change",()=>draw(true));$("timeWindow").addEventListener("change",()=>draw(true));$("playbackSpeed").addEventListener("change",()=>{video.playbackRate=Number($("playbackSpeed").value);});
for(const event of ["timeupdate","seeked","loadedmetadata","pause"])video.addEventListener(event,()=>draw(true));
video.addEventListener("error",()=>{if(state.result&&video.getAttribute("src"))$("mediaError").hidden=false;});
$("scoreCanvas").addEventListener("click",(e)=>{if(state.result)seek(canvasTime(e));});$("overviewCanvas").addEventListener("click",(e)=>{if(state.result)seek(canvasTime(e,true));});
$("scoreCanvas").addEventListener("mousemove",(e)=>{if(state.result){state.hoverTime=canvasTime(e);drawScores(video.currentTime);}});$("scoreCanvas").addEventListener("mouseleave",()=>{state.hoverTime=null;if(state.result)drawScores(video.currentTime);});
for(const id of ["scoreCanvas","overviewCanvas"])$(id).addEventListener("keydown",(e)=>{if(e.key==="ArrowLeft"||e.key==="ArrowRight"){e.preventDefault();seek(video.currentTime+(e.key==="ArrowRight"?1:-1));}else if(e.key==="Home"){e.preventDefault();seek(0);}else if(e.key==="End"){e.preventDefault();seek(state.result?.duration_seconds||0);}});
for(const id of ["downloadAll","downloadClips"])$(id).addEventListener("click",()=>toast("正在准备全部回合，完成后浏览器会开始下载"));
if(window.ResizeObserver)new ResizeObserver(()=>draw(true)).observe($("main-content")||document.querySelector(".main-content"));else window.addEventListener("resize",()=>draw(true));
function animate(){if(!video.paused&&!video.ended)draw();requestAnimationFrame(animate);}requestAnimationFrame(animate);initialize();setInterval(poll,2000);
