import React from 'react';
import ReactMarkdown from 'react-markdown';
import { jsPDF } from 'jspdf';

export type ObsMessage = {
  id: string; role: string; content: string;
  imagesJson?: string | null; imageBase64?: string | null; imageMimeType?: string | null; createdAt: string;
};
export type ObsChild = {
  first_name: string; last_name: string; date_of_birth?: string | null;
  age_group?: string | null; gender?: string | null; start_date?: string | null;
  doctor_name?: string | null; allergies?: string | null; medical_conditions?: string | null;
};
interface Props { child: ObsChild; messages: ObsMessage[]; onClose: () => void; }

function stripMd(t: string) {
  return t.replace(/#{1,6}\s+/gm,'').replace(/\*{1,3}(.+?)\*{1,3}/g,'$1')
    .replace(/`+([^`]*)`+/g,'$1').replace(/^\s*[-*+]\s+/gm,'• ')
    .replace(/\[(.+?)\]\(.+?\)/g,'$1').replace(/^>\s+/gm,'').replace(/\n{3,}/g,'\n\n').trim();
}
function fmtD(iso?: string | null) {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('en-US',{year:'numeric',month:'short',day:'numeric'});
}
function fmtTs(iso: string) {
  return new Date(iso).toLocaleString('en-US',{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'});
}
function imgCount(msg: ObsMessage) {
  if (msg.imagesJson) { try { return JSON.parse(msg.imagesJson).length; } catch { /* not valid json */ } }
  return msg.imageBase64 ? 1 : 0;
}

function buildPDF(child: ObsChild, messages: ObsMessage[]) {
  const doc = new jsPDF({orientation:'portrait',unit:'mm',format:'a4'});
  const PW=210,PH=297,M=16,CW=PW-M*2,BOT=PH-14;
  let y=M;
  const np=()=>{doc.addPage();y=M;};
  const need=(h:number)=>{if(y+h>BOT)np();};

  // Header
  doc.setFillColor(109,40,217); doc.rect(0,0,PW,30,'F');
  doc.setFont('helvetica','bold'); doc.setFontSize(17); doc.setTextColor(255,255,255);
  doc.text('CHILD OBSERVATION REPORT',M,13);
  doc.setFont('helvetica','normal'); doc.setFontSize(8.5); doc.setTextColor(216,180,254);
  doc.text(`Generated: ${fmtD(new Date().toISOString())}`,M,22);
  doc.text('CONFIDENTIAL',PW-M,22,{align:'right'});
  y=38;

  // Child info box
  doc.setFillColor(245,243,255); doc.setDrawColor(196,181,253);
  doc.roundedRect(M,y,CW,34,2.5,2.5,'FD');
  doc.setFont('helvetica','bold'); doc.setFontSize(7.5); doc.setTextColor(91,33,182);
  doc.text('CHILD INFORMATION',M+5,y+7);
  const c1=M+5,c2=M+CW/2+2;
  const name=`${child.first_name} ${child.last_name}`;
  const rows:[string,string,string,string][]=[
    ['Name:',name,'Age Group:',child.age_group||'—'],
    ['DOB:',fmtD(child.date_of_birth),'Start Date:',fmtD(child.start_date)],
    ['Gender:',child.gender||'—','Doctor:',child.doctor_name||'—'],
  ];
  rows.forEach(([l1,v1,l2,v2],i)=>{
    const ry=y+14+i*7;
    doc.setFont('helvetica','bold'); doc.setFontSize(8.5); doc.setTextColor(75,85,99);
    doc.text(l1,c1,ry); doc.setFont('helvetica','normal'); doc.setTextColor(17,24,39); doc.text(v1,c1+20,ry);
    doc.setFont('helvetica','bold'); doc.setTextColor(75,85,99);
    doc.text(l2,c2,ry); doc.setFont('helvetica','normal'); doc.setTextColor(17,24,39); doc.text(v2,c2+22,ry);
  });
  y+=42;

  // Alerts (allergies / conditions)
  const alerts=[child.allergies,child.medical_conditions].filter(Boolean);
  if(alerts.length>0){
    need(12);
    doc.setFillColor(254,242,242); doc.setDrawColor(252,165,165);
    doc.roundedRect(M,y,CW,10,2,2,'FD');
    doc.setFont('helvetica','bold'); doc.setFontSize(7.5); doc.setTextColor(185,28,28);
    doc.text('⚠ HEALTH ALERTS',M+4,y+4.5);
    doc.setFont('helvetica','normal'); doc.setFontSize(8); doc.setTextColor(153,27,27);
    doc.text(alerts.join('  |  '),M+4,y+8.5,{maxWidth:CW-8});
    y+=14;
  }

  // Section header
  const aiN=messages.filter(m=>m.role==='assistant').length;
  need(10);
  doc.setFillColor(109,40,217); doc.rect(M,y,CW,8,'F');
  doc.setFont('helvetica','bold'); doc.setFontSize(8.5); doc.setTextColor(255,255,255);
  doc.text('AI BEHAVIORAL OBSERVATIONS',M+4,y+5.5);
  doc.text(`${aiN} observation${aiN!==1?'s':''}  ·  ${messages.length} messages`,PW-M-4,y+5.5,{align:'right'});
  y+=12;

  if(messages.length===0){
    need(10); doc.setFont('helvetica','italic'); doc.setFontSize(9); doc.setTextColor(156,163,175);
    doc.text('No conversation recorded.',M,y); y+=10;
  }

  messages.forEach((msg,idx)=>{
    const isUser=msg.role==='user';
    const label=isUser?'STAFF NOTE':'AI OBSERVATION';
    const lrgb:[number,number,number]=isUser?[124,58,237]:[79,70,229];
    const clean=stripMd(msg.content);
    const lines=doc.setFontSize(9)&&doc.splitTextToSize(clean,CW-4) as string[];
    const n=imgCount(msg);
    const blockH=6+lines.length*4.6+(n>0?5:0)+4;
    need(blockH);

    if(idx>0){doc.setDrawColor(221,214,254);doc.line(M,y,M+CW,y);y+=3;}

    // Label + timestamp row
    doc.setFont('helvetica','bold'); doc.setFontSize(8); doc.setTextColor(...lrgb);
    doc.text(label,M,y);
    doc.setFont('helvetica','normal'); doc.setFontSize(7.5); doc.setTextColor(156,163,175);
    doc.text(fmtTs(msg.createdAt),PW-M,y,{align:'right'});
    y+=5;

    // Content
    doc.setFont('helvetica','normal'); doc.setFontSize(9); doc.setTextColor(31,41,55);
    lines.forEach((line:string)=>{need(5);doc.text(line,M,y);y+=4.6;});
    if(n>0){
      doc.setFont('helvetica','italic'); doc.setFontSize(7.5); doc.setTextColor(156,163,175);
      doc.text(`📷 ${n} image${n!==1?'s':''} attached`,M,y); y+=4;
    }
    y+=3;
  });

  // Footer on every page
  const total=doc.getNumberOfPages();
  for(let p=1;p<=total;p++){
    doc.setPage(p);
    doc.setFillColor(249,250,251); doc.rect(0,PH-12,PW,12,'F');
    doc.setDrawColor(229,231,235); doc.line(0,PH-12,PW,PH-12);
    doc.setFont('helvetica','normal'); doc.setFontSize(7); doc.setTextColor(156,163,175);
    doc.text(`${name} — Child Observation Report`,M,PH-5);
    doc.text(`Page ${p} of ${total}`,PW-M,PH-5,{align:'right'});
  }

  const slug=`${child.first_name}-${child.last_name}`.toLowerCase().replace(/\s+/g,'-');
  doc.save(`observation-${slug}-${new Date().toISOString().slice(0,10)}.pdf`);
}

// ─── Component ───────────────────────────────────────────────────────────────

const ObservationReport: React.FC<Props> = ({ child, messages, onClose }) => {
  const childName = `${child.first_name} ${child.last_name}`;
  const today = fmtD(new Date().toISOString());
  const aiMsgs = messages.filter(m => m.role === 'assistant');
  const alerts = [child.allergies, child.medical_conditions].filter(Boolean);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm" onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[90vh] flex flex-col" onClick={e => e.stopPropagation()}>

        {/* Modal header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100 shrink-0">
          <div>
            <h2 className="text-lg font-bold text-gray-900">Observation Report</h2>
            <p className="text-xs text-gray-500 mt-0.5">{aiMsgs.length} AI observation{aiMsgs.length !== 1 ? 's' : ''} · {childName}</p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => buildPDF(child, messages)}
              className="flex items-center gap-1.5 px-4 py-2 bg-violet-600 hover:bg-violet-700 text-white text-sm font-medium rounded-lg transition-colors"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              Download PDF
            </button>
            <button onClick={onClose} className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg">
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
            </button>
          </div>
        </div>

        {/* Document preview */}
        <div className="flex-1 overflow-y-auto bg-gray-100 p-6">
          <div className="bg-white shadow-md rounded-xl overflow-hidden max-w-xl mx-auto text-sm">

            {/* Header */}
            <div className="bg-violet-700 px-6 py-5">
              <h1 className="text-white font-bold text-xl tracking-tight">Child Observation Report</h1>
              <p className="text-violet-200 text-xs mt-1">Generated: {today} &nbsp;·&nbsp; Confidential</p>
            </div>

            {/* Child info */}
            <div className="bg-violet-50 border-b border-violet-100 px-6 py-4">
              <h3 className="text-xs font-bold text-violet-800 uppercase tracking-widest mb-3">Child Information</h3>
              <div className="grid grid-cols-2 gap-x-6 gap-y-1.5">
                {[['Name', childName],['DOB', fmtD(child.date_of_birth)],['Age Group', child.age_group||'—'],['Start Date', fmtD(child.start_date)],['Gender', child.gender||'—'],['Doctor', child.doctor_name||'—']].map(([l,v])=>(
                  <div key={l}><span className="font-medium text-gray-500">{l}:</span> <span className="text-gray-900">{v}</span></div>
                ))}
              </div>
            </div>

            {/* Health alerts */}
            {alerts.length > 0 && (
              <div className="bg-red-50 border-b border-red-100 px-6 py-3 flex items-start gap-2">
                <svg className="w-4 h-4 text-red-500 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" /></svg>
                <div>
                  <p className="text-xs font-bold text-red-700 uppercase tracking-wide">Health Alerts</p>
                  <p className="text-xs text-red-600 mt-0.5">{alerts.join(' · ')}</p>
                </div>
              </div>
            )}

            {/* Messages */}
            <div className="px-6 py-4">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-xs font-bold text-violet-800 uppercase tracking-widest">AI Behavioral Observations</h3>
                <span className="text-xs text-gray-400">{aiMsgs.length} observation{aiMsgs.length !== 1 ? 's' : ''}</span>
              </div>

              {messages.length === 0 ? (
                <p className="text-gray-400 text-center py-8">No conversation yet.</p>
              ) : (
                <div className="space-y-4">
                  {messages.map((msg) => {
                    const isUser = msg.role === 'user';
                    const n = imgCount(msg);
                    return (
                      <div key={msg.id} className={`border-l-2 pl-4 ${isUser ? 'border-purple-300' : 'border-violet-400'}`}>
                        <div className="flex items-center justify-between mb-1">
                          <span className={`text-xs font-bold uppercase tracking-wide ${isUser ? 'text-purple-600' : 'text-violet-700'}`}>
                            {isUser ? 'Staff Note' : 'AI Observation'}
                          </span>
                          <span className="text-xs text-gray-400">{fmtTs(msg.createdAt)}</span>
                        </div>
                        <div className={`prose prose-xs max-w-none leading-relaxed text-gray-700 ${isUser ? '' : 'prose-violet'}`}>
                          <ReactMarkdown>{msg.content}</ReactMarkdown>
                        </div>
                        {n > 0 && <p className="text-xs text-gray-400 mt-1">📷 {n} image{n !== 1 ? 's' : ''} attached</p>}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="bg-gray-50 border-t border-gray-100 px-6 py-3 flex justify-between text-xs text-gray-400">
              <span>{childName} · Observation Report</span>
              <span>{today}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ObservationReport;