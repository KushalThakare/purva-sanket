const $ = id => document.getElementById(id);
const set = (id,value) => { $(id).textContent=value ?? "—"; };
const points=[];
let requests=0, refreshing=false, lastSample=null, currentFaults={};
const faultLabels={
  temperature_missing:"Temperature input missing",
  camera_missing:"Camera observation unavailable",
  cooling_missing:"Cooling feedback absent",
  telemetry_delayed:"Delay telemetry by 8 seconds",
  telemetry_repeated:"Repeat the last telemetry packet",
  response_ack_missing:"Command acknowledgement missing",
  response_feedback_missing:"Motor feedback unavailable",
  response_feedback_running:"Motor feedback reports running"
};
function list(id,values){
  $(id).replaceChildren();
  for(const value of values){const li=document.createElement("li");li.textContent=value;$(id).append(li);}
}
const when=t=>t===null||t===undefined?"—":new Date(t*1000).toLocaleTimeString();
const seconds=n=>n===null||n===undefined?"No warning yet":n.toFixed(1)+" s after run start";
async function command(path,body,message){
  try{
    const response=await fetch(path,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
    const value=await response.json();
    if(!response.ok)throw Error(typeof value.detail==="string"?value.detail:JSON.stringify(value.detail));
    set("message",message);
    await refresh();
    return value;
  }catch(error){set("message",error.message);return null;}
}
async function action(kind,note=""){
  return command("/api/action",{kind,operator:$("operator").value,note},"Operator action recorded.");
}
const titles=["Normal monitoring","Weak warnings","Cooling mismatch","Worker exposure","Sensor failure","Recovery"];
titles.forEach((title,index)=>{
  const button=document.createElement("button");button.className="scene";button.dataset.scene=index+1;
  const number=document.createElement("b");number.textContent="SCENE 0"+(index+1);
  button.append(number,document.createTextNode(title));
  button.onclick=()=>command("/api/scene",{scene:index+1},"Scene requested. Wait for the next input packet.");
  $("scenes").append(button);
});
for(const [name,label] of Object.entries(faultLabels)){
  const button=document.createElement("button");button.className="fault-button";button.dataset.fault=name;
  button.setAttribute("aria-pressed","false");button.textContent=label;
  button.onclick=async()=>{
    button.disabled=true;
    try{await command("/api/fault",{name,enabled:!currentFaults[name]},"Fault test updated. New packets pass through the selected test.");}
    finally{button.disabled=false;}
  };
  $("fault-controls").append(button);
}
$("manual").onclick=()=>command("/api/scene",{scene:0},"Manual Wokwi controls requested.");
$("ml-demo").onclick=()=>command("/api/scene",{scene:7},"ML pattern requested. Use Production mode and compare after a valid 10-sample window.");
$("simulated-vision").onclick=()=>command("/api/vision/simulated",{},"Scripted presence enabled; this is a simulated observation.");
$("clear-faults").onclick=()=>command("/api/faults/clear",{},"Test faults cleared. Restore the Wokwi feedback switch and resolve any open episode.");
$("mode").onchange=()=>command("/api/mode",{mode:$("mode").value},"Operating mode selected.");
$("ack").onclick=()=>action("acknowledge");
$("record").onclick=()=>action("corrective_action",$("note").value);
$("stop").onclick=()=>action("stop");
$("restart").onclick=()=>action("restart");
function chart(){
  const canvas=$("chart"),ctx=canvas.getContext("2d"),w=canvas.width,h=canvas.height;
  ctx.clearRect(0,0,w,h);ctx.strokeStyle="#e8edf1";ctx.lineWidth=1;
  for(let i=0;i<5;i++){const y=12+(h-24)*i/4;ctx.beginPath();ctx.moveTo(8,y);ctx.lineTo(w-8,y);ctx.stroke();}
  for(const [key,color,low,high] of [["t","#d96a2a",30,65],["v","#377ca8",0,1]]){
    ctx.strokeStyle=color;ctx.lineWidth=2;ctx.beginPath();let drawing=false;
    points.forEach((point,index)=>{
      if(point[key]===null||point[key]===undefined){drawing=false;return;}
      const x=8+(w-16)*index/Math.max(points.length-1,1);
      const y=h-12-(h-24)*Math.min(1,Math.max(0,(point[key]-low)/(high-low)));
      if(drawing)ctx.lineTo(x,y);else ctx.moveTo(x,y);drawing=true;
    });ctx.stroke();
  }
}
async function renderHistory(){
  const response=await fetch("/api/history");if(!response.ok)return;
  const h=await response.json();$("history").replaceChildren();
  for(const ep of h.episodes){
    const row=document.createElement("tr");
    for(const value of [ep.id.slice(0,8),when(ep.opened_at),ep.status,ep.acknowledged?"Acknowledged":"Pending",when(ep.closed_at)]){
      const cell=document.createElement("td");cell.textContent=value;row.append(cell);
    }$("history").append(row);
  }
  if(!h.episodes.length){
    const row=document.createElement("tr"),cell=document.createElement("td");cell.colSpan=5;
    cell.textContent="No equipment warning episode has been opened.";row.append(cell);$("history").append(row);
  }
  list("events",h.events.slice(0,12).map(e=>when(e.created_at)+" · "+e.kind.replaceAll("_"," ")+" · "+e.detail_json));
  list("commands",(h.response_commands||[]).slice(0,6).map(c=>when(c.requested_at)+" · "+c.command_id.slice(0,8)+" · "+(c.requested_running?"RUN":"STOP")+" · "+c.status));
}
function renderVerification(r){
  if(!r)return;
  set("response-status",r.status.replaceAll("_"," "));
  $("response-status").className="verification-status "+(r.confirmed?"normal":r.status==="UNCONFIRMED"||r.status==="PROTOCOL_REQUIRED"?"fault":"warn");
  set("response-detail",r.status==="PROTOCOL_REQUIRED"?"Update the Wokwi sketch and diagram to enable the command/feedback protocol.":r.detail);
  set("response-target",r.requested_running?"RUN":"STOP");set("response-id",r.command_id?.slice(0,12));
  set("response-ack",r.acknowledged_at!==null&&r.acknowledged_at!==undefined?"Received at "+when(r.acknowledged_at):"Waiting");
  set("response-feedback",r.feedback_running===null||r.feedback_running===undefined?"Unavailable / unmatched":r.feedback_running?"RUNNING":"STOPPED");
  set("response-source",r.feedback_source);
  set("response-timing",r.confirmed?"Confirmed in "+(r.confirmation_seconds??0).toFixed(2)+" s":r.seconds_remaining===null?"Awaiting device session / publication":r.seconds_remaining.toFixed(1)+" s remaining");
}
function renderComparison(c){
  if(!c)return;
  for(const [prefix,path] of [["rule",c.rules],["hybrid",c.hybrid]]){
    set(prefix+"-risk",path.risk);$(prefix+"-risk").className=path.warning?"warn":"normal";
    list(prefix+"-reasons",path.reasons.length?path.reasons:["No current equipment-warning evidence."]);
  }
  const run=c.run;
  set("rule-first",run?seconds(run.rule_first_warning_seconds):"Waiting for an accepted input");
  set("hybrid-first",run?seconds(run.hybrid_first_warning_seconds):"Waiting for an accepted input");
  let result="Both paths use identical input-health and critical protective checks.";
  if(c.hybrid_lead_seconds!==null){
    result=c.hybrid_lead_seconds>0?"Hybrid first warning was "+c.hybrid_lead_seconds.toFixed(1)+" s earlier in this run.":c.hybrid_lead_seconds<0?"Rules first warning was "+(-c.hybrid_lead_seconds).toFixed(1)+" s earlier in this run.":"Both paths first warned at the same accepted sample.";
  }else if(run&&run.hybrid_first_warning_at!==null&&run.rule_first_warning_at===null){
    result="Only the hybrid path has warned so far in this run. This does not establish an accident prediction.";
  }
  set("comparison-result",result);
  set("comparison-counts",run?"Run "+run.id.slice(0,8)+" · "+run.sample_count+" accepted samples · Rules: "+run.rule_warning_samples+" warning samples / "+run.rule_warning_events+" warning starts · Hybrid: "+run.hybrid_warning_samples+" warning samples / "+run.hybrid_warning_events+" warning starts":"Waiting for a comparison run.");
}
async function refresh(){
  if(refreshing)return;refreshing=true;
  try{
    const response=await fetch("/api/state");if(!response.ok)throw Error("Backend unavailable");
    const s=await response.json();
    set("source",s.input_mode==="offline"?"LOCAL REPLAY · SYNTHETIC INPUTS":"WOKWI / MQTT · SIMULATED INPUTS");
    set("connection",s.input_mode==="offline"?"Replay running on laptop":s.mqtt_connected?"Broker connected":"Broker disconnected");
    set("risk",s.risk);$("risk").className=s.risk==="NORMAL"?"normal":"warn";
    set("health",s.monitoring_health);$("health").className=s.monitoring_health==="AVAILABLE"?"normal":"fault";
    set("age",s.telemetry_age_s===null?"No telemetry":"Last telemetry "+s.telemetry_age_s.toFixed(1)+" s ago");
    set("temperature",s.temperature_c===null?"Unavailable":s.temperature_c.toFixed(1)+" °C");
    set("vibration",s.vibration_rms_ms2===null?"Unavailable":s.vibration_rms_ms2.toFixed(2)+" m/s²");
    set("episode-status",s.episode?s.episode.status+" · "+s.episode.id.slice(0,8):"No open episode");
    set("scene-name",s.scene_name);
    document.querySelectorAll(".scene").forEach(b=>b.classList.toggle("selected",Number(b.dataset.scene)===s.scene));
    $("mode").value=s.mode;
    const flag=v=>v===null||v===undefined?"Unknown":v?"ON / present":"OFF / absent";
    set("cooling-command",flag(s.cooling_command));set("cooling-feedback",flag(s.cooling_feedback));
    set("guard",s.guard_closed===undefined||s.guard_closed===null?"Unknown":s.guard_closed?"Closed":"Open");
    set("worker",s.vision.fresh?s.vision.present?"Inside zone":"Outside zone":"Unknown");
    set("vision-source",s.vision.source==="vision"?"YOLO / video or webcam":s.vision.source==="simulated"?"Scripted test input":"Unavailable");
    set("motor",(s.motor_command?"RUN":"STOP")+" / "+(s.motor_feedback===null?"Replay only":s.motor_feedback?"ON":"OFF"));
    set("explanation",s.current_evidence.length?"Contributing evidence from the current observations:":s.episode?"Earlier evidence remains unresolved. Closure requires valid recovery and operator response.":"No current equipment warning. Monitoring health is reported separately.");
    list("current-evidence",s.current_evidence.map(e=>e.text));
    list("faults",s.faults.length?s.faults:["No current input-health fault"]);
    list("memory",s.episode?Object.values(JSON.parse(s.episode.evidence_json)):["No open episode"]);
    set("ml",s.ml.status);
    set("ml-score",s.ml.status==="WARMUP"?s.ml.samples+"/"+s.ml.required+" samples":s.ml.decision_score!==undefined?"Decision score: "+s.ml.decision_score:"No valid feature window");
    set("feature-values",s.ml.values?"Window features: temperature mean "+s.ml.values[0]+" °C; slope "+s.ml.values[1]+" °C/s; vibration mean "+s.ml.values[2]+" m/s²; maximum "+s.ml.values[3]+" m/s².":"Explicit rules remain active while the model waits for a valid window.");
    set("recovery",s.episode?.status==="RECOVERING"?"Valid recovery "+s.recovery_seconds+"/"+s.recovery_required+" s":"Acknowledgement + corrective action + confirmed STOP + 15 s valid recovery");
    const sample=s.device_session+":"+s.sample_seq;
    if(sample!==lastSample){lastSample=sample;points.push({t:s.temperature_c,v:s.vibration_rms_ms2});if(points.length>60)points.shift();chart();}
    renderVerification(s.response);renderComparison(s.comparison);
    visualizerState = s;
    drawApplicationVisualizer();
    const f=s.fault_injection;
    if(f){
      currentFaults=f.enabled;
      document.querySelectorAll(".fault-button").forEach(b=>b.setAttribute("aria-pressed",String(!!f.enabled[b.dataset.fault])));
      set("fault-summary",(f.active.length?f.active.length+" active test fault(s)":"No injected faults")+" · "+f.withheld_packets+" withheld · "+f.expired_packets+" expired · "+f.rejected_packets+" rejected packets");
    }
    if(s.bridge_error)set("message",s.bridge_error);
    requests++;if(requests%5===1)await renderHistory();
  }catch(error){
    set("connection","Backend unavailable");set("health","UNAVAILABLE");$("health").className="fault";
    set("response-status","BACKEND UNAVAILABLE");$("response-status").className="verification-status fault";
  }finally{refreshing=false;}
}

let rotorAngle=0, visualizerState=null;
function drawApplicationVisualizer(){
  const canvas=$("app-visualizer");if(!canvas)return;
  const ctx=canvas.getContext("2d"),w=canvas.width,h=canvas.height,s=visualizerState;
  ctx.fillStyle="#111827";ctx.fillRect(0,0,w,h);
  ctx.strokeStyle="rgba(255,255,255,0.05)";ctx.lineWidth=1;
  for(let x=0;x<w;x+=40){ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,h);ctx.stroke();}
  for(let y=0;y<h;y+=40){ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(w,y);ctx.stroke();}
  if(!s){
    ctx.fillStyle="#94a3b8";ctx.font="14px Arial";ctx.textAlign="center";
    ctx.fillText("Waiting for live IoT telemetry stream...",w/2,h/2);return;
  }
  ctx.fillStyle="#064e3b";ctx.strokeStyle="#10b981";ctx.lineWidth=2;
  ctx.fillRect(25,20,240,195);ctx.strokeRect(25,20,240,195);
  ctx.fillStyle="#ecfdf5";ctx.font="bold 12px Arial";ctx.textAlign="left";
  ctx.fillText("ESP32 IoT GATEWAY BOARD",38,42);
  ctx.fillStyle="#9ca3af";ctx.font="10px Arial";
  ctx.fillText("Topic: "+(s.topic||"purva/demo/telemetry"),38,58);
  const leds=[
    {label:"NORMAL",active:s.monitoring_health==="AVAILABLE"&&s.risk==="NORMAL",color:"#22c55e"},
    {label:"WARNING",active:s.risk!=="NORMAL",color:"#f59e0b"},
    {label:"DEGRADED",active:s.monitoring_health!=="AVAILABLE",color:"#ef4444"},
    {label:"MOTOR",active:s.motor_command,color:"#3b82f6"},
    {label:"COOLING",active:s.cooling_command,color:"#f97316"}
  ];
  leds.forEach((led,idx)=>{
    const ly=82+idx*22;
    ctx.beginPath();ctx.arc(48,ly,6,0,Math.PI*2);
    if(led.active){ctx.fillStyle=led.color;ctx.shadowColor=led.color;ctx.shadowBlur=8;}
    else{ctx.fillStyle="#374151";ctx.shadowBlur=0;}
    ctx.fill();ctx.shadowBlur=0;
    ctx.fillStyle=led.active?"#ffffff":"#9ca3af";ctx.font="10px Arial";
    ctx.fillText(led.label+" LED",62,ly+3);
  });
  ctx.fillStyle="#1e293b";ctx.fillRect(135,75,118,130);
  ctx.fillStyle="#38bdf8";ctx.font="10px monospace";
  ctx.fillText("SEQ:  "+(s.sample_seq||0),142,95);
  ctx.fillText("TEMP: "+(s.temperature_c!==null?s.temperature_c.toFixed(1)+"C":"N/A"),142,115);
  ctx.fillText("VIB:  "+(s.vibration_rms_ms2!==null?s.vibration_rms_ms2.toFixed(2):"N/A"),142,135);
  ctx.fillText("ML:   "+(s.ml?.status||"WARMUP"),142,155);
  ctx.fillText("MODE: "+(s.mode||"PROD"),142,175);
  ctx.fillText("RISK: "+(s.risk||"NORMAL"),142,195);

  const cx=580,cy=125,temp=s.temperature_c??35,vib=s.vibration_rms_ms2??0.1;
  const heatRadius=70+Math.min(30,Math.max(0,temp-30)*1.5);
  const grad=ctx.createRadialGradient(cx,cy,15,cx,cy,heatRadius);
  if(temp>=60){grad.addColorStop(0,"rgba(239,68,68,0.8)");grad.addColorStop(1,"rgba(239,68,68,0)");}
  else if(temp>=45){grad.addColorStop(0,"rgba(245,158,11,0.6)");grad.addColorStop(1,"rgba(245,158,11,0)");}
  else{grad.addColorStop(0,"rgba(59,130,246,0.35)");grad.addColorStop(1,"rgba(59,130,246,0)");}
  ctx.fillStyle=grad;ctx.beginPath();ctx.arc(cx,cy,heatRadius,0,Math.PI*2);ctx.fill();

  ctx.fillStyle="#334155";ctx.strokeStyle="#64748b";ctx.lineWidth=3;
  ctx.fillRect(cx-65,cy-55,130,110);ctx.strokeRect(cx-65,cy-55,130,110);

  if(s.motor_command)rotorAngle+=0.15+vib*0.1;
  ctx.save();ctx.translate(cx,cy);ctx.rotate(rotorAngle);
  ctx.strokeStyle=s.motor_command?"#60a5fa":"#94a3b8";ctx.lineWidth=4;
  for(let b=0;b<4;b++){ctx.rotate(Math.PI/2);ctx.beginPath();ctx.moveTo(0,0);ctx.lineTo(0,30);ctx.stroke();}
  ctx.restore();

  if(vib>0.05){
    ctx.strokeStyle=vib>=0.45?"#ef4444":"#f59e0b";ctx.lineWidth=2;
    const ripple=(Date.now()/100)%25;
    ctx.beginPath();ctx.ellipse(cx,cy+60,60+ripple,12+ripple/3,0,0,Math.PI*2);ctx.stroke();
  }

  ctx.fillStyle="#1e293b";ctx.fillRect(cx-40,cy-95,80,36);
  ctx.strokeStyle="#475569";ctx.strokeRect(cx-40,cy-95,80,36);
  ctx.fillStyle="#94a3b8";ctx.font="9px Arial";ctx.textAlign="center";
  ctx.fillText("COOLING DUCT",cx,cy-82);
  if(s.cooling_command){
    if(s.cooling_feedback){
      ctx.fillStyle="#38bdf8";
      const particleOffset=(Date.now()/15)%30;
      for(let px=cx-25+particleOffset;px<cx+25;px+=12){
        ctx.beginPath();ctx.arc(px,cy-70,3,0,Math.PI*2);ctx.fill();
      }
    }else{
      ctx.fillStyle=(Math.floor(Date.now()/300)%2===0)?"#ef4444":"#7f1d1d";
      ctx.fillRect(cx-38,cy-93,76,32);
      ctx.fillStyle="#ffffff";ctx.font="bold 9px Arial";
      ctx.fillText("AIRFLOW FAULT",cx,cy-74);
    }
  }

  const isWorkerInside=s.vision&&s.vision.fresh&&s.vision.present;
  const zoneBorder=isWorkerInside&&s.risk!=="NORMAL"?"#ef4444":isWorkerInside?"#f59e0b":"#10b981";
  ctx.fillStyle="rgba(15,23,42,0.7)";ctx.fillRect(850,20,320,195);
  ctx.strokeStyle=zoneBorder;ctx.lineWidth=isWorkerInside?3:2;
  ctx.setLineDash(isWorkerInside?[6,4]:[]);
  ctx.strokeRect(860,30,300,175);ctx.setLineDash([]);
  ctx.fillStyle=zoneBorder;ctx.font="bold 11px Arial";ctx.textAlign="left";
  ctx.fillText("HAZARD ZONE PERIMETER (YOLO)",870,48);

  const wx=isWorkerInside?1010:880,wy=125;
  ctx.fillStyle="#fde047";ctx.beginPath();ctx.arc(wx,wy-25,9,0,Math.PI*2);ctx.fill();
  ctx.fillStyle="#eab308";ctx.fillRect(wx-11,wy-36,22,5);
  ctx.fillStyle=isWorkerInside?"#ea580c":"#0284c7";ctx.fillRect(wx-7,wy-16,14,26);
  ctx.fillStyle="#1e293b";ctx.fillRect(wx-6,wy+10,4,18);ctx.fillRect(wx+2,wy+10,4,18);
  if(isWorkerInside){
    ctx.strokeStyle="#38bdf8";ctx.lineWidth=2;
    ctx.strokeRect(wx-22,wy-42,44,72);
    ctx.fillStyle="#0284c7";ctx.fillRect(wx-22,wy-54,68,12);
    ctx.fillStyle="#ffffff";ctx.font="bold 8px Arial";
    ctx.fillText("PERSON 96%",wx-19,wy-45);
  }else{
    ctx.fillStyle="#22c55e";ctx.font="10px Arial";ctx.textAlign="center";
    ctx.fillText("Safe Outside Perimeter",915,182);
  }

  ctx.fillStyle="rgba(15,23,42,0.9)";ctx.fillRect(0,h-24,w,24);
  ctx.fillStyle=s.risk==="NORMAL"?"#4ade80":"#f87171";ctx.font="bold 11px Arial";ctx.textAlign="left";
  ctx.fillText("APPLICATION STATUS: "+s.risk+" | HEALTH: "+s.monitoring_health+" | MOTOR: "+(s.motor_command?"RUNNING":"STOPPED")+" | "+(s.explanation||""),12,h-7);
}

function animateVisualizer(){
  drawApplicationVisualizer();
  requestAnimationFrame(animateVisualizer);
}
requestAnimationFrame(animateVisualizer);

refresh();setInterval(refresh,1000);
