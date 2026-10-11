"use client";
import { useEffect, useRef, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
type Course = {id:string;title:string};
type Task = {id:string;text:string;language:string;recording_id:string|null;status:string|null};
async function request(path:string, opts:RequestInit={}){
  const res=await fetch(API+path,opts);
  const data=await res.json().catch(()=>({detail:"Unexpected response"}));
  if(!res.ok) throw new Error(typeof data.detail==="string"?data.detail:JSON.stringify(data.detail));
  return data;
}
export default function Home(){
  const [tab,setTab]=useState<"student"|"admin">("student");
  const [token,setToken]=useState("");
  const [adminKey,setAdminKey]=useState("");
  const [consent,setConsent]=useState(false);
  const [familiarity,setFamiliarity]=useState("");
  const [english,setEnglish]=useState("");
  const [mic,setMic]=useState("");
  const [courses,setCourses]=useState<Course[]>([]);
  const [course,setCourse]=useState("");
  const [tasks,setTasks]=useState<Task[]>([]);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [notice,setNotice]=useState("");
  const [active,setActive]=useState<string|null>(null);
  const [audioUrl,setAudioUrl]=useState("");
  const [blob,setBlob]=useState<Blob|null>(null);
  const [recordedFor,setRecordedFor]=useState<string|null>(null);
  const [courseName,setCourseName]=useState("");
  const [newPrompt,setNewPrompt]=useState("");
  const [adminCourse,setAdminCourse]=useState("");
  const [reviewList,setReviewList]=useState<any[]>([]);
  const [reviewText,setReviewText]=useState<Record<string,string>>({});
  const recorder=useRef<MediaRecorder|null>(null);
  const chunks=useRef<BlobPart[]>([]);
  const stream=useRef<MediaStream|null>(null);
  const urlRef=useRef("");
  useEffect(()=>{request("/api/v1/courses").then(setCourses).catch(()=>{});return()=>{stream.current?.getTracks().forEach(x=>x.stop());if(urlRef.current)URL.revokeObjectURL(urlRef.current)}},[]);
  function alertError(e:unknown){setError(e instanceof Error?e.message:String(e));setNotice("")}
  async function signup(){
    setBusy(true);setError("");
    try{
      const r=await request("/api/v1/participants",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({consent,consent_version:"pilot-v1",familiarity,english_level:english,microphone:mic})});
      setToken(r.participant_token);setNotice("Đã đăng ký. Hãy lưu mã truy cập cá nhân trước khi đóng trang."); 
    }catch(e){alertError(e)}finally{setBusy(false)}
  }
  async function loadTasks(id=course){
    setBusy(true);setError("");
    try{setTasks(await request("/api/v1/tasks?course_id="+encodeURIComponent(id),{headers:{"x-participant-token":token}}))}
    catch(e){alertError(e)}finally{setBusy(false)}
  }
  function clearAudio(){
    if(urlRef.current){URL.revokeObjectURL(urlRef.current);urlRef.current=""}
    setAudioUrl("");setBlob(null);setRecordedFor(null);
  }
  async function start(id:string){
    clearAudio();setError("");
    try{
      if(!window.MediaRecorder?.isTypeSupported("audio/webm;codecs=opus"))throw new Error("Trình duyệt không hỗ trợ WebM/Opus. Dùng Chrome/Edge desktop.");
      const s=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true}});
      stream.current=s;chunks.current=[];
      const r=new MediaRecorder(s,{mimeType:"audio/webm;codecs=opus"});
      r.ondataavailable=e=>{if(e.data.size)chunks.current.push(e.data)};
      r.onstop=()=>{
        const output=new Blob(chunks.current,{type:"audio/webm"});
        setBlob(output);setRecordedFor(id);const url=URL.createObjectURL(output);urlRef.current=url;setAudioUrl(url);
        stream.current?.getTracks().forEach(t=>t.stop());stream.current=null;
      };
      r.start();recorder.current=r;setActive(id);
    }catch(e){alertError(e)}
  }
  function stop(){recorder.current?.stop();recorder.current=null;setActive(null)}
  async function upload(id:string){
    if(!blob||recordedFor!==id){setError("Bản ghi không thuộc câu này");return;}
    setBusy(true);setError("");
    try{
      const form=new FormData();form.append("prompt_id",id);form.append("audio",blob,"utterance.webm");
      await request("/api/v1/recordings",{method:"POST",headers:{"x-participant-token":token},body:form});
      setNotice("Đã gửi ghi âm, chờ kiểm duyệt.");clearAudio();await loadTasks();
    }catch(e){alertError(e)}finally{setBusy(false)}
  }
  const ah={"x-admin-key":adminKey,"Content-Type":"application/json"};
  async function createCourse(){
    try{const x=await request("/api/v1/admin/courses",{method:"POST",headers:ah,body:JSON.stringify({title:courseName})});
      setAdminCourse(x.id);setNotice("Đã tạo môn: "+x.title+" — ID "+x.id)}catch(e){alertError(e)}
  }
  async function createPrompt(){
    try{
      const x=await request("/api/v1/admin/courses/"+encodeURIComponent(adminCourse)+"/prompts",
        {method:"POST",headers:ah,body:JSON.stringify({text:newPrompt,language:"vi-en"})});
      await request("/api/v1/admin/prompts/"+x.id+"/publish",{method:"POST",headers:ah});
      setNotice("Đã tạo và xuất bản câu nói.");setNewPrompt("");
      setCourses(await request("/api/v1/courses"));
    }catch(e){alertError(e)}
  }
  async function reviews(){
    try{setReviewList(await request("/api/v1/admin/recordings",{headers:{"x-admin-key":adminKey}}))}
    catch(e){alertError(e)}
  }
  async function review(id:string,approved:boolean){
    try{await request("/api/v1/admin/recordings/"+id+"/review",{method:"POST",headers:ah,
      body:JSON.stringify({approved,transcript:reviewText[id]||""})});await reviews();setNotice("Đã lưu đánh giá")}
    catch(e){alertError(e)}
  }
  const card:React.CSSProperties={padding:20,background:"white",border:"1px solid #dbe3ed",borderRadius:14,marginBottom:18};
  const field:React.CSSProperties={display:"block",padding:"11px 12px",border:"1px solid #aebcc9",borderRadius:8,width:"100%",maxWidth:620,boxSizing:"border-box",margin:"8px 0 14px"};
  const button:React.CSSProperties={padding:"10px 16px",background:"#1767a5",color:"white",border:"none",borderRadius:8,cursor:"pointer",margin:"4px 6px 4px 0"};
  return <main style={{maxWidth:900,margin:"0 auto",padding:"32px 20px",fontFamily:"Arial,sans-serif"}}>
    <p style={{color:"#1767a5",fontWeight:700}}>LIEMWHISPER · DATA COLLECTION PILOT</p>
    <h1>Thu thập giọng nói Việt–Anh</h1>
    <p>Nghiên cứu nhận dạng thuật ngữ tiếng Anh trong lời nói tiếng Việt. Tham gia tự nguyện; ghi âm được kiểm duyệt trước khi dùng trong nghiên cứu.</p>
    <p style={{color:"#9b3f13"}}>Bản pilot chưa dành cho thu dữ liệu sinh viên thật trước khi hoàn thiện phê duyệt, xác thực và quy trình rút lại sự đồng ý.</p>
    <nav><button style={button} onClick={()=>setTab("student")}>Sinh viên</button><button style={button} onClick={()=>setTab("admin")}>Quản trị</button></nav>
    {error&&<p role="alert" style={{color:"#af2929"}}>{error}</p>}
    {notice&&<p role="status" style={{color:"#146c51"}}>{notice}</p>}
    {tab==="student"?<>
      <section style={card}><h2>1. Đồng ý và khảo sát</h2>
        <p>Ghi âm được lưu để nghiên cứu AI speech–text. Không bắt buộc tham gia; chưa cung cấp thông tin định danh trong bản pilot.</p>
        <label><input type="checkbox" checked={consent} onChange={e=>setConsent(e.target.checked)}/> Tôi đồng ý tham gia thử nghiệm ghi âm cho mục đích nghiên cứu.</label>
        <label style={{display:"block",marginTop:12}}>Mức độ quen thuộc với môn học
          <select style={field} value={familiarity} onChange={e=>setFamiliarity(e.target.value)}>
            <option value="">Chọn (không bắt buộc)</option><option>Mới học</option><option>Đã học</option><option>Thành thạo</option>
          </select></label>
        <label>Mức tiếng Anh tự đánh giá<input style={field} value={english} onChange={e=>setEnglish(e.target.value)} maxLength={100}/></label>
        <label>Loại microphone<input style={field} value={mic} onChange={e=>setMic(e.target.value)} maxLength={100}/></label>
        <button style={button} disabled={!consent||busy} onClick={signup}>Đăng ký tham gia</button>
        <label style={{display:"block",marginTop:12}}>Mã truy cập đã nhận (lưu để tiếp tục khi quay lại)
          <input style={field} value={token} onChange={e=>setToken(e.target.value)} placeholder="Participant token" type="password"/>
        </label>
      </section>
      <section style={card}><h2>2. Chọn môn và nhận câu nói</h2>
        <select style={field} value={course} onChange={e=>{setCourse(e.target.value);setTasks([]);clearAudio()}}>
          <option value="">Chọn môn học</option>{courses.map(c=><option key={c.id} value={c.id}>{c.title}</option>)}
        </select>
        <button style={button} disabled={!token||!course||busy} onClick={()=>loadTasks()}>Lấy danh sách câu</button>
      </section>
      <section style={card}><h2>3. Ghi âm từng câu</h2>
        {tasks.length===0?<p>Chưa có câu nói được giao.</p>:tasks.map(t=><div key={t.id} style={{padding:14,borderBottom:"1px solid #e2e8f0"}}>
          <p><strong>{t.text}</strong></p><p style={{color:"#667587"}}>Ngôn ngữ: {t.language} · {t.status||"Chưa ghi âm"}</p>
          {!t.recording_id&&<>{active===t.id?<button style={{...button,background:"#b52e35"}} onClick={stop}>Dừng ghi âm</button>:
          <button style={button} disabled={!!active||busy} onClick={()=>start(t.id)}>Bắt đầu ghi âm</button>}
          {audioUrl&&!active&&recordedFor===t.id&&<div><audio controls src={audioUrl}/><br/><button style={button} disabled={busy} onClick={()=>upload(t.id)}>Gửi bản ghi này</button>
          <button style={{...button,background:"#526271"}} onClick={clearAudio}>Ghi lại</button></div>}</>}
        </div>)}
      </section>
    </>:<>
      <section style={card}><h2>Admin · Tạo môn học và câu thu âm</h2>
        <label>Admin API key<input style={field} type="password" value={adminKey} onChange={e=>setAdminKey(e.target.value)}/></label>
        <label>Tên môn<input style={field} value={courseName} onChange={e=>setCourseName(e.target.value)}/></label>
        <button style={button} onClick={createCourse}>Tạo môn</button>
        <label>ID môn học<input style={field} value={adminCourse} onChange={e=>setAdminCourse(e.target.value)}/></label>
        <label>Câu nói cần sinh viên đọc<textarea style={{...field,minHeight:90}} value={newPrompt} onChange={e=>setNewPrompt(e.target.value)}/></label>
        <button style={button} onClick={createPrompt}>Tạo và xuất bản câu</button>
      </section>
      <section style={card}><h2>Admin · Kiểm duyệt ghi âm</h2>
        <button style={button} onClick={reviews}>Tải danh sách ghi âm</button>
        {reviewList.map(r=><div key={r.id} style={{padding:14,borderBottom:"1px solid #e2e8f0"}}>
          <p><strong>{r.text}</strong> · {r.status}</p>
          <p>ID: {r.id}</p>
          <p>Audio riêng tư: truy xuất bằng API <code>/api/v1/admin/recordings/{r.id}/audio</code> với admin key (chưa có player xác thực ở UI).</p>
          <textarea style={{...field,minHeight:70}} placeholder="Bản chép lời đúng theo audio thực tế" value={reviewText[r.id]??r.transcript??""}
            onChange={e=>setReviewText(prev=>({...prev,[r.id]:e.target.value}))}/>
          <button style={button} onClick={()=>review(r.id,true)}>Duyệt</button>
          <button style={{...button,background:"#9a3434"}} onClick={()=>review(r.id,false)}>Từ chối</button>
        </div>)}
      </section>
    </>}
    <footer style={{color:"#657184",fontSize:13,marginTop:40}}>LiemWhisper · Research prototype · Không công khai recordings hoặc token truy cập.</footer>
  </main>;
}
