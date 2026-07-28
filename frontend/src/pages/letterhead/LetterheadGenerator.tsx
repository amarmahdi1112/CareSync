import React, { useState, useRef } from 'react';
import logoWithBg from '../../assets/images/svgs/Logo_with_bg.svg';
import {
  PrinterIcon,
  PhotoIcon,
  DocumentTextIcon,
  SparklesIcon,
  UserIcon,
  EnvelopeIcon,
  MapPinIcon,
  PhoneIcon,
  GlobeAltIcon,
  CloudArrowUpIcon,
  TrashIcon,
  ClockIcon
} from '@heroicons/react/24/outline';
import { useNotificationStore } from '../../stores';
import { jsPDF } from 'jspdf';
import { api } from '../../api/client';
import { useApiQuery } from '../../api/hooks';

// Helper to safely parse bold and italic styling rules in real time
function renderFormattedText(text: string) {
  if (!text) return null;

  return text.split('\n').map((line, lineIdx) => {
    // Regex splits by: ***bold-italic***, **bold**, *italic*, _italic_
    const parts = line.split(/(\*\*\*.*?\*\*\*|\*\*.*?\*\*|\*.*?\*|_.*?_)/g);
    
    const formattedLine = parts.map((part, partIdx) => {
      if (part.startsWith('***') && part.endsWith('***')) {
        return <strong key={partIdx} className="font-extrabold italic">{part.slice(3, -3)}</strong>;
      }
      if (part.startsWith('**') && part.endsWith('**')) {
        return <strong key={partIdx} className="font-extrabold">{part.slice(2, -2)}</strong>;
      }
      if (part.startsWith('*') && part.endsWith('*')) {
        return <em key={partIdx} className="italic font-medium">{part.slice(1, -1)}</em>;
      }
      if (part.startsWith('_') && part.endsWith('_')) {
        return <em key={partIdx} className="italic font-medium">{part.slice(1, -1)}</em>;
      }
      return part;
    });

    return (
      <React.Fragment key={lineIdx}>
        {formattedLine}
        {lineIdx < text.split('\n').length - 1 && <br />}
      </React.Fragment>
    );
  });
}

// Standard themes with styles
type ThemeId = 'modern_teal' | 'royal_serif' | 'clean_minimal' | 'playful_daycare';

interface LetterheadState {
  companyName: string;
  tagline: string;
  address: string;
  phone: string;
  email: string;
  website: string;
  logoUrl: string;
  
  refNo: string;
  date: string;
  subject: string;
  
  recipientName: string;
  recipientTitle: string;
  recipientOrg: string;
  recipientAddress: string;
  
  letterBody: string;
  
  signatoryName: string;
  signatoryTitle: string;
  signatureType: 'typed' | 'uploaded';
  signatureText: string;
  signatureUrl: string;
  
  footerText: string;
  theme: ThemeId;
  accentColor: string;
}

const THEME_PRESETS: Record<ThemeId, { name: string; fontHeader: string; fontBody: string; borderStyle: string; align: 'left' | 'center' | 'right' | 'between' }> = {
  modern_teal: {
    name: 'Modern Teal',
    fontHeader: 'font-sans font-extrabold tracking-tight',
    fontBody: 'font-sans text-gray-700',
    borderStyle: 'border-b-4 border-teal-500',
    align: 'between'
  },
  royal_serif: {
    name: 'Royal Serif',
    fontHeader: 'font-serif font-bold italic tracking-wide',
    fontBody: 'font-serif text-gray-800 leading-relaxed',
    borderStyle: 'border-b-2 border-double border-amber-600 py-1',
    align: 'center'
  },
  clean_minimal: {
    name: 'Clean Minimalist',
    fontHeader: 'font-sans font-light tracking-widest uppercase',
    fontBody: 'font-sans text-gray-600',
    borderStyle: 'border-b border-gray-200',
    align: 'left'
  },
  playful_daycare: {
    name: 'Playful Daycare',
    fontHeader: 'font-sans font-black tracking-normal text-purple-600',
    fontBody: 'font-sans text-gray-700 font-medium',
    borderStyle: 'border-b-4 border-dashed border-sky-400',
    align: 'between'
  }
};

const DEFAULT_BODY = `Dear Parents,

We are excited to share that our upcoming summer camp registration is now officially open! Discoverers Daycare is planning a variety of exciting field trips, interactive science projects, and outdoor adventures for all age groups.

Please review the attached schedule and pricing details. If you would like to reserve a spot for your child, kindly complete the registration form and return it to our front desk by next Friday.

Should you have any questions, please feel free to reach out to us. Thank you for your continued support!

Warm regards,`;

export default function LetterheadGenerator() {
  const [state, setState] = useState<LetterheadState>({
    companyName: "Discoverers' Daycare",
    tagline: 'Learning, Growing, and Laughing Together',
    address: '10625 117 St NW, Edmonton, AB T5H 3M9',
    phone: '780-482-1234',
    email: 'info@discoverersdaycare.com',
    website: 'www.discoverersdaycare.com',
    logoUrl: logoWithBg,
    
    refNo: 'DD-2026-0042',
    date: new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' }),
    subject: 'ANNOUNCEMENT: Summer Camp Registration Open',
    
    recipientName: 'All Discoverers Families',
    recipientTitle: 'Daycare & OSC Parents',
    recipientOrg: 'Discoverers Daycare Community',
    recipientAddress: 'Edmonton, Alberta',
    
    letterBody: DEFAULT_BODY,
    
    signatoryName: 'Fowzia Ali',
    signatoryTitle: 'Executive Director',
    signatureType: 'typed',
    signatureText: 'Fowzia Ali',
    signatureUrl: '',
    
    footerText: 'Discoverers Daycare Decouvreurs Garderie Inc. is a licensed childcare provider in Alberta.',
    theme: 'modern_teal',
    accentColor: '#0d9488' // Teal-600
  });

  const [activeTab, setActiveTab] = useState<'header' | 'recipient' | 'body' | 'signature' | 'style' | 'history'>('header');
  const logoInputRef = useRef<HTMLInputElement>(null);
  const sigInputRef = useRef<HTMLInputElement>(null);

  // DB History Hooks
  const { data: letterheads = [], loading: historyLoading, error: historyError, refetch: refetchHistory } = useApiQuery<any[]>('/resources/letterheads', { limit: 1000, sort: 'updated_at', order: 'desc' });
  const historyData = { letterheads };
  const { success: showSuccess, error: showError } = useNotificationStore();

  // Save Modal States
  const [loadedId, setLoadedId] = useState<string | null>(null);
  const [saveTitle, setSaveTitle] = useState('');
  const [isSaveModalOpen, setIsSaveModalOpen] = useState(false);
  const [saveAsNew, setSaveAsNew] = useState(false);

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
    const { name, value } = e.target;
    setState(prev => ({ ...prev, [name]: value }));
  };

  const handleLogoUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      const url = URL.createObjectURL(file);
      setState(prev => ({ ...prev, logoUrl: url }));
    }
  };

  const handleSignatureUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      const url = URL.createObjectURL(file);
      setState(prev => ({ ...prev, signatureUrl: url, signatureType: 'uploaded' }));
    }
  };

  const handlePrint = () => {
    window.print();
  };

  const [isDownloadOpen, setIsDownloadOpen] = useState(false);

  // Exporters
  const handleDownloadPDF = () => {
    const doc = new jsPDF({
      orientation: 'portrait',
      unit: 'mm',
      format: 'a4'
    });

    const margin = 20;
    const pageWidth = doc.internal.pageSize.getWidth();
    const pageHeight = doc.internal.pageSize.getHeight();
    const contentWidth = pageWidth - (margin * 2);
    
    let currentY = 25;

    // Draw header text
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(18);
    doc.setTextColor(13, 148, 136); // Teal-600 color
    doc.text(state.companyName, margin, currentY);
    
    currentY += 6;
    if (state.tagline) {
      doc.setFont('helvetica', 'oblique');
      doc.setFontSize(9);
      doc.setTextColor(100, 116, 139);
      doc.text(state.tagline, margin, currentY);
    }

    // Contact info block (right-aligned)
    doc.setFont('helvetica', 'normal');
    doc.setFontSize(8);
    doc.setTextColor(100, 116, 139);
    const contacts = [
      state.address,
      state.phone ? `Phone: ${state.phone}` : null,
      state.email ? `Email: ${state.email}` : null,
      state.website ? `Website: ${state.website}` : null
    ].filter(Boolean) as string[];

    let contactY = 22;
    contacts.forEach(c => {
      const w = doc.getTextWidth(c);
      doc.text(c, pageWidth - margin - w, contactY);
      contactY += 4;
    });

    currentY = Math.max(currentY + 10, contactY + 4);

    // Header separator line
    doc.setDrawColor(13, 148, 136);
    doc.setLineWidth(0.8);
    doc.line(margin, currentY, pageWidth - margin, currentY);
    currentY += 10;

    // Reference & Date
    doc.setFont('helvetica', 'normal');
    doc.setFontSize(9);
    doc.setTextColor(100, 116, 139);
    if (state.refNo) {
      doc.text(`Ref: ${state.refNo}`, margin, currentY);
    }
    const dateW = doc.getTextWidth(state.date);
    doc.text(state.date, pageWidth - margin - dateW, currentY);
    currentY += 10;

    // Recipient Details
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(9.5);
    doc.setTextColor(15, 23, 42);
    if (state.recipientName) {
      doc.text(state.recipientName, margin, currentY);
      currentY += 5;
    }
    doc.setFont('helvetica', 'normal');
    doc.setFontSize(9);
    doc.setTextColor(71, 85, 105);
    if (state.recipientTitle) {
      doc.text(state.recipientTitle, margin, currentY);
      currentY += 4.5;
    }
    if (state.recipientOrg) {
      doc.text(state.recipientOrg, margin, currentY);
      currentY += 4.5;
    }
    if (state.recipientAddress) {
      doc.text(state.recipientAddress, margin, currentY);
      currentY += 5;
    }
    currentY += 4;

    // Subject Line
    if (state.subject) {
      doc.setFont('helvetica', 'bold');
      doc.setFontSize(10);
      doc.setTextColor(15, 23, 42);
      const cleanSubj = `SUBJECT: ${state.subject.toUpperCase().replace(/\*\*|\*|_/g, '')}`;
      doc.text(cleanSubj, margin, currentY);
      
      // Accent border line under subject
      doc.setDrawColor(13, 148, 136);
      doc.setLineWidth(0.4);
      doc.line(margin, currentY + 1.5, margin + doc.getTextWidth(cleanSubj), currentY + 1.5);
      currentY += 12;
    }

    // Letter Body Text
    doc.setFont('helvetica', 'normal');
    doc.setFontSize(10);
    doc.setTextColor(51, 65, 85);
    
    const cleanBody = state.letterBody.replace(/\*\*|\*|_/g, '');
    const paragraphs = cleanBody.split('\n');
    
    paragraphs.forEach((pText) => {
      const lines = doc.splitTextToSize(pText || ' ', contentWidth);
      lines.forEach((line: string) => {
        if (currentY > pageHeight - 35) {
          doc.addPage();
          currentY = 25;
        }
        doc.text(line, margin, currentY);
        currentY += 6;
      });
      currentY += 3; // spacing between paragraphs
    });
    
    currentY += 8;

    // Signature Area
    if (currentY > pageHeight - 45) {
      doc.addPage();
      currentY = 25;
    }

    // Signature line
    doc.setDrawColor(156, 163, 175);
    doc.setLineWidth(0.3);
    doc.line(margin, currentY + 8, margin + 56, currentY + 8);

    if (state.signatureType === 'typed' && state.signatureText) {
      doc.setFont('courier', 'oblique');
      doc.setFontSize(13);
      doc.setTextColor(13, 148, 136);
      doc.text(state.signatureText, margin + 4, currentY + 5.5);
    } else if (state.signatureType === 'uploaded' && state.signatureUrl && state.signatureUrl.startsWith('data:')) {
      try {
        doc.addImage(state.signatureUrl, 'PNG', margin + 2, currentY, 40, 7.5);
      } catch (e) {
        console.warn(e);
      }
    }

    currentY += 13;
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(9);
    doc.setTextColor(15, 23, 42);
    doc.text(state.signatoryName, margin, currentY);
    
    currentY += 4.5;
    doc.setFont('helvetica', 'normal');
    doc.setFontSize(8.5);
    doc.setTextColor(100, 116, 139);
    doc.text(state.signatoryTitle, margin, currentY);

    // Footer text
    if (state.footerText) {
      doc.setFont('helvetica', 'normal');
      doc.setFontSize(8);
      doc.setTextColor(148, 163, 184);
      const cleanFooter = state.footerText.replace(/\*\*|\*|_/g, '');
      const footerLines = doc.splitTextToSize(cleanFooter, contentWidth);
      
      let footerY = pageHeight - 15 - (footerLines.length * 4);
      footerLines.forEach((line: string) => {
        const textWidth = doc.getTextWidth(line);
        doc.text(line, (pageWidth - textWidth) / 2, footerY);
        footerY += 4;
      });
    }

    const filename = `${saveTitle || 'letterhead_' + new Date().getTime()}.pdf`;
    doc.save(filename);
    showSuccess("Downloaded PDF", `Saved letterhead document as "${filename}".`);
  };

  const handleDownloadDoc = () => {
    const cleanBody = state.letterBody.replace(/\r\n/g, '<br/>').replace(/\n/g, '<br/>');
    const content = `
      <html xmlns:o='urn:schemas-microsoft-com:office:office' xmlns:w='urn:schemas-microsoft-com:office:word' xmlns='http://www.w3.org/TR/REC-html40'>
        <head>
          <meta charset="utf-8">
          <title>${state.subject.replace(/\*\*|\*|_/g, '')}</title>
          <style>
            body { font-family: 'Arial', sans-serif; line-height: 1.6; color: #334155; }
            .header { border-bottom: 2px solid ${state.accentColor}; padding-bottom: 15px; margin-bottom: 30px; }
            .title { font-size: 22px; color: ${state.accentColor}; font-weight: bold; }
            .tagline { font-size: 11px; color: #64748b; font-style: italic; }
            .metadata { margin-bottom: 25px; font-size: 11px; color: #64748b; }
            .recipient { margin-bottom: 25px; font-size: 12px; }
            .subject { font-weight: bold; font-size: 12px; border-left: 3px solid ${state.accentColor}; padding-left: 10px; margin-bottom: 25px; }
            .body { font-size: 12px; margin-bottom: 35px; }
            .signature-line { border-top: 1px solid #9ca3af; width: 220px; margin-top: 40px; margin-bottom: 6px; }
            .signatory { font-size: 11px; font-weight: bold; }
            .title-role { font-size: 10px; color: #64748b; }
            .footer { font-size: 9px; color: #94a3b8; border-top: 1px solid #e2e8f0; padding-top: 10px; text-align: center; margin-top: 50px; }
          </style>
        </head>
        <body>
          <div class="header">
            <div class="title">${state.companyName}</div>
            <div class="tagline">${state.tagline}</div>
            <div style="font-size: 10px; color: #64748b; margin-top: 5px;">
              ${state.address} | Phone: ${state.phone} | Email: ${state.email}
            </div>
          </div>
          <table style="width: 100%; font-size: 11px; color: #64748b; margin-bottom: 25px;">
            <tr>
              <td>Ref: ${state.refNo}</td>
              <td style="text-align: right;">${state.date}</td>
            </tr>
          </table>
          <div class="recipient">
            <strong>${state.recipientName}</strong><br/>
            ${state.recipientTitle}<br/>
            ${state.recipientOrg}<br/>
            ${state.recipientAddress}
          </div>
          <div class="subject">SUBJECT: ${state.subject.toUpperCase().replace(/\*\*|\*|_/g, '')}</div>
          <div class="body">${cleanBody}</div>
          <div>
            <div class="signature-line"></div>
            <div class="signatory">${state.signatoryName}</div>
            <div class="title-role">${state.signatoryTitle}</div>
          </div>
          <div class="footer">${state.footerText}</div>
        </body>
      </html>
    `;
    
    const blob = new Blob(['\ufeff' + content], { type: 'application/msword' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    const filename = `${saveTitle || 'letterhead_' + new Date().getTime()}.doc`;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    showSuccess("Downloaded DOC", `Saved letterhead document as "${filename}".`);
  };

  const selectTheme = (themeId: ThemeId) => {
    let accent = '#0d9488'; // Teal
    if (themeId === 'royal_serif') accent = '#d97706'; // Amber-600
    if (themeId === 'clean_minimal') accent = '#4b5563'; // Gray-600
    if (themeId === 'playful_daycare') accent = '#9333ea'; // Purple-600

    setState(prev => ({ ...prev, theme: themeId, accentColor: accent }));
  };

  // Bold / Italic insertion helper for text inputs and textareas
  const insertFormat = (fieldId: 'subject' | 'letterBody', formatType: 'bold' | 'italic') => {
    const el = document.getElementsByName(fieldId)[0] as HTMLTextAreaElement | HTMLInputElement;
    if (!el) return;

    const start = el.selectionStart ?? 0;
    const end = el.selectionEnd ?? 0;
    const text = el.value;
    const selected = text.substring(start, end);
    
    let replacement = '';
    if (formatType === 'bold') {
      replacement = `**${selected || 'bold text'}**`;
    } else {
      replacement = `*${selected || 'italic text'}*`;
    }

    const newValue = text.substring(0, start) + replacement + text.substring(end);
    setState(prev => ({ ...prev, [fieldId]: newValue }));
    
    // Reset focus and selection
    setTimeout(() => {
      el.focus();
      const offset = formatType === 'bold' ? 2 : 1;
      el.setSelectionRange(start + offset, start + offset + (selected || 'text').length);
    }, 0);
  };

  // Click handler to launch save modal
  const handleSaveClick = () => {
    if (loadedId) {
      const loadedLh = historyData?.letterheads?.find((lh: any) => lh.id === loadedId);
      if (loadedLh) {
        setSaveTitle(loadedLh.title);
      }
    } else {
      setSaveTitle(state.subject.replace(/\*\*|\*|_/g, '') || '');
    }
    setSaveAsNew(false);
    setIsSaveModalOpen(true);
  };

  // Mutation trigger to post state data to backend
  const handleSaveSubmit = async () => {
    try {
      const input = {
        id: (!saveAsNew && loadedId) ? loadedId : undefined,
        title: saveTitle.trim(),
        date: state.date,
        ref_no: state.refNo,
        subject: state.subject,
        recipient_name: state.recipientName,
        recipient_title: state.recipientTitle,
        recipient_org: state.recipientOrg,
        recipient_address: state.recipientAddress,
        letter_body: state.letterBody,
        signatory_name: state.signatoryName,
        signatory_title: state.signatoryTitle,
        signature_type: state.signatureType,
        signature_text: state.signatureText,
        signature_url: state.signatureUrl,
        footer_text: state.footerText,
        theme: state.theme,
        accent_color: state.accentColor,
      };

      const saved = (!saveAsNew && loadedId)
        ? await api.resources.update<any>('letterheads', loadedId, input)
        : await api.resources.create<any>('letterheads', input);
      
      if (saved?.id) {
        showSuccess("Saved Successfully", `Letterhead "${saveTitle}" has been saved to your history.`);
        if (!saveAsNew || !loadedId) {
          setLoadedId(saved.id);
        }
        setIsSaveModalOpen(false);
        refetchHistory();
      }
    } catch (err: any) {
      showError("Save Error", err.message || "Failed to save letterhead to history");
    }
  };

  // Loads history item properties into React state
  const loadLetterhead = (lh: any) => {
    setState({
      companyName: state.companyName,
      tagline: state.tagline,
      address: state.address,
      phone: state.phone,
      email: state.email,
      website: state.website,
      logoUrl: state.logoUrl,
      
      refNo: lh.ref_no || '',
      date: lh.date || '',
      subject: lh.subject || '',
      recipientName: lh.recipient_name || '',
      recipientTitle: lh.recipient_title || '',
      recipientOrg: lh.recipient_org || '',
      recipientAddress: lh.recipient_address || '',
      letterBody: lh.letter_body || '',
      signatoryName: lh.signatory_name || '',
      signatoryTitle: lh.signatory_title || '',
      signatureType: lh.signature_type as any,
      signatureText: lh.signature_text || '',
      signatureUrl: lh.signature_url || '',
      footerText: lh.footer_text || '',
      theme: lh.theme as any,
      accentColor: lh.accent_color || '#0d9488',
    });
    setLoadedId(lh.id);
    showSuccess("Loaded Document", `Loaded "${lh.title}" successfully.`);
  };

  // Triggers delete mutation
  const handleDeleteClick = async (id: string, title: string) => {
    if (!window.confirm(`Are you sure you want to delete the letterhead "${title}"?`)) {
      return;
    }
    try {
      await api.resources.remove('letterheads', id);
      showSuccess("Document Deleted", `Removed "${title}" from your history.`);
      if (loadedId === id) {
        setLoadedId(null);
      }
      refetchHistory();
    } catch (err: any) {
      showError("Delete Error", err.message || "Failed to delete letterhead");
    }
  };

  const currentTheme = THEME_PRESETS[state.theme];

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col md:flex-row">
      {/* Import Signature font dynamically */}
      <link href="https://fonts.googleapis.com/css2?family=Dancing+Script:wght@600&family=Playwrite+AU+VIC:wght@300&family=Great+Vibes&display=swap" rel="stylesheet" />

      {/* Printing Stylesheet Injection */}
      <style>{`
        /* Global preview & print styles */
        .letterhead-sheet {
          font-synthesis: weight style !important;
        }
        .letterhead-sheet .font-sans {
          font-family: Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif !important;
        }
        .letterhead-sheet .font-serif {
          font-family: Georgia, Cambria, "Times New Roman", Times, serif !important;
        }

        @media print {
          /* Force page margins and size */
          @page {
            size: A4;
            margin: 0;
          }
          
          /* Hide scrollbars, disable scrolling height limits on body and html */
          body, html {
            background: white !important;
            margin: 0 !important;
            padding: 0 !important;
            height: auto !important;
            overflow: visible !important;
            -webkit-print-color-adjust: exact !important;
            print-color-adjust: exact !important;
          }

          /* Hide all UI elements, overlays, and sidebars explicitly */
          nav, header, aside, .no-print, button, .tabs-container, .controls-panel, .w-64, [class*="bg-black"], [class*="bg-opacity-"], .fixed, [id*="-focus-trapper-"], [class*="-focus-trapper-"] {
            display: none !important;
          }

          /* Neutralize the global grid layout wrapper containers */
          div.flex.h-screen {
            display: block !important;
            height: auto !important;
            overflow: visible !important;
            background: transparent !important;
          }

          div.flex-1.flex.flex-col.overflow-hidden {
            display: block !important;
            height: auto !important;
            overflow: visible !important;
            background: transparent !important;
          }

          main.flex-1, main.overflow-y-auto {
            display: block !important;
            height: auto !important;
            overflow: visible !important;
            padding: 0 !important;
            margin: 0 !important;
            background: transparent !important;
          }

          div.container, div.mx-auto {
            width: 100% !important;
            max-width: 100% !important;
            padding: 0 !important;
            margin: 0 !important;
            display: block !important;
            height: auto !important;
            overflow: visible !important;
          }

          /* Fit the letterhead precisely to page */
          .print-wrapper {
            position: absolute !important;
            left: 0 !important;
            top: 0 !important;
            width: 100% !important;
            height: auto !important;
            margin: 0 !important;
            padding: 0 !important;
            border: none !important;
            box-shadow: none !important;
            background: white !important;
            display: block !important;
            overflow: visible !important;
          }

          .letterhead-sheet {
            width: 210mm !important;
            height: 297mm !important;
            margin: 0 auto !important; /* Center on sheet */
            padding: 20mm !important;
            border: none !important;
            box-shadow: none !important;
            background: white !important;
            box-sizing: border-box !important;
            page-break-after: avoid !important;
            page-break-before: avoid !important;
            page-break-inside: avoid !important;
          }
        }
      `}</style>

      {/* Left panel: Editor Controls */}
      <div className="w-full md:w-[450px] bg-white border-r border-gray-200 flex flex-col h-[calc(100vh-64px)] md:sticky md:top-16 overflow-y-auto no-print controls-panel">
        <div className="p-6 border-b border-gray-100 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-gray-900 flex items-center gap-2">
              <DocumentTextIcon className="w-6 h-6 text-purple-600" />
              Letterhead Creator
            </h1>
            <p className="text-xs text-gray-500 mt-1">Design & export professional documents</p>
          </div>
          
          <div className="flex items-center gap-2">
            <button
              onClick={handleSaveClick}
              className="flex items-center gap-1 bg-white hover:bg-gray-50 text-gray-700 border border-gray-200 text-xs font-semibold py-2 px-3 rounded-lg shadow-sm transition-all"
              title="Save to database history"
            >
              <CloudArrowUpIcon className="w-4 h-4 text-purple-600" />
              Save
            </button>

            <div className="relative">
              <button
                onClick={() => setIsDownloadOpen(!isDownloadOpen)}
                className="flex items-center gap-1 bg-white hover:bg-gray-50 text-gray-700 border border-gray-200 text-xs font-semibold py-2 px-3 rounded-lg shadow-sm transition-all"
                title="Download options"
              >
                <span>Download</span>
                <span className="text-[9px] text-gray-400 font-bold">▼</span>
              </button>
              
              {isDownloadOpen && (
                <>
                  <div className="fixed inset-0 z-10" onClick={() => setIsDownloadOpen(false)}></div>
                  <div className="absolute right-0 mt-1 w-44 bg-white border border-gray-200 rounded-lg shadow-lg py-1 z-20 animate-fadeIn">
                    <button
                      onClick={() => {
                        handleDownloadPDF();
                        setIsDownloadOpen(false);
                      }}
                      className="w-full text-left px-4 py-2 text-xs text-gray-700 hover:bg-purple-50 hover:text-purple-600 transition font-semibold"
                    >
                      PDF Document (.pdf)
                    </button>
                    <button
                      onClick={() => {
                        handleDownloadDoc();
                        setIsDownloadOpen(false);
                      }}
                      className="w-full text-left px-4 py-2 text-xs text-gray-700 hover:bg-purple-50 hover:text-purple-600 transition font-semibold"
                    >
                      Word Document (.doc)
                    </button>
                  </div>
                </>
              )}
            </div>

            <button
              onClick={handlePrint}
              className="flex items-center gap-1 bg-purple-650 hover:bg-purple-755 text-white text-xs font-semibold py-2 px-3.5 rounded-lg shadow-sm transition-all"
            >
              <PrinterIcon className="w-4 h-4" />
              Print
            </button>
          </div>
        </div>

        {/* Tab Selection */}
        <div className="flex border-b border-gray-100 px-4 py-2 bg-gray-50/50 gap-1 overflow-x-auto tabs-container">
          {[
            { id: 'header', label: 'Header', icon: SparklesIcon },
            { id: 'recipient', label: 'Recipient', icon: UserIcon },
            { id: 'body', label: 'Body', icon: DocumentTextIcon },
            { id: 'signature', label: 'Sign & Footer', icon: PhotoIcon },
            { id: 'style', label: 'Templates', icon: SparklesIcon },
            { id: 'history', label: 'History', icon: ClockIcon }
          ].map(t => (
            <button
              key={t.id}
              onClick={() => setActiveTab(t.id as any)}
              className={`flex items-center gap-1.5 py-1.5 px-3 rounded-md text-xs font-semibold whitespace-nowrap transition-all ${
                activeTab === t.id
                  ? 'bg-purple-100 text-purple-750 shadow-sm'
                  : 'text-gray-600 hover:bg-gray-100'
              }`}
            >
              <t.icon className="w-3.5 h-3.5" />
              {t.label}
            </button>
          ))}
        </div>

        <div className="p-6 flex-1 space-y-5">
          {/* TAB 1: HEADER DETAILS */}
          {activeTab === 'header' && (
            <div className="space-y-4 animate-fadeIn">
              <div>
                <label className="block text-xs font-bold text-gray-700 uppercase tracking-wider mb-1.5">Company / Daycare Name</label>
                <input
                  type="text"
                  name="companyName"
                  value={state.companyName}
                  onChange={handleInputChange}
                  className="w-full text-sm border border-gray-200 rounded-lg p-2.5 focus:border-purple-500 focus:ring-1 focus:ring-purple-500"
                />
              </div>

              <div>
                <label className="block text-xs font-bold text-gray-700 uppercase tracking-wider mb-1.5">Tagline / Motto</label>
                <input
                  type="text"
                  name="tagline"
                  value={state.tagline}
                  onChange={handleInputChange}
                  className="w-full text-sm border border-gray-200 rounded-lg p-2.5 focus:border-purple-500 focus:ring-1 focus:ring-purple-500"
                />
              </div>

              <div>
                <label className="block text-xs font-bold text-gray-700 uppercase tracking-wider mb-1.5">Logo</label>
                <div className="flex items-center gap-3">
                  {state.logoUrl && (
                    <img src={state.logoUrl} alt="Logo" className="w-12 h-12 object-contain bg-gray-50 border border-gray-100 p-1.5 rounded-lg" />
                  )}
                  <input
                    type="file"
                    ref={logoInputRef}
                    onChange={handleLogoUpload}
                    accept="image/*"
                    className="hidden"
                  />
                  <button
                    type="button"
                    onClick={() => logoInputRef.current?.click()}
                    className="text-xs bg-gray-100 hover:bg-gray-200 font-semibold py-2 px-3 border border-gray-200 rounded-lg transition"
                  >
                    Change Logo
                  </button>
                  {state.logoUrl !== logoWithBg && (
                    <button
                      type="button"
                      onClick={() => setState(prev => ({ ...prev, logoUrl: logoWithBg }))}
                      className="text-xs text-red-500 hover:text-red-700 font-semibold"
                    >
                      Reset Default
                    </button>
                  )}
                </div>
              </div>

              <div className="border-t border-gray-100 pt-4 space-y-3.5">
                <h3 className="text-xs font-bold text-gray-400 uppercase tracking-wider">Contact Info</h3>
                
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Address</label>
                  <input
                    type="text"
                    name="address"
                    value={state.address}
                    onChange={handleInputChange}
                    className="w-full text-sm border border-gray-200 rounded-lg p-2 focus:border-purple-500"
                  />
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">Phone</label>
                    <input
                      type="text"
                      name="phone"
                      value={state.phone}
                      onChange={handleInputChange}
                      className="w-full text-sm border border-gray-200 rounded-lg p-2 focus:border-purple-500"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">Email</label>
                    <input
                      type="text"
                      name="email"
                      value={state.email}
                      onChange={handleInputChange}
                      className="w-full text-sm border border-gray-200 rounded-lg p-2 focus:border-purple-500"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Website</label>
                  <input
                    type="text"
                    name="website"
                    value={state.website}
                    onChange={handleInputChange}
                    className="w-full text-sm border border-gray-200 rounded-lg p-2 focus:border-purple-500"
                  />
                </div>
              </div>
            </div>
          )}

          {/* TAB 2: RECIPIENT & METADATA */}
          {activeTab === 'recipient' && (
            <div className="space-y-4 animate-fadeIn">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-bold text-gray-700 uppercase tracking-wider mb-1.5">Date</label>
                  <input
                    type="text"
                    name="date"
                    value={state.date}
                    onChange={handleInputChange}
                    className="w-full text-sm border border-gray-200 rounded-lg p-2.5 focus:border-purple-500"
                  />
                </div>
                <div>
                  <label className="block text-xs font-bold text-gray-700 uppercase tracking-wider mb-1.5">Ref #</label>
                  <input
                    type="text"
                    name="refNo"
                    value={state.refNo}
                    onChange={handleInputChange}
                    className="w-full text-sm border border-gray-200 rounded-lg p-2.5 focus:border-purple-500"
                  />
                </div>
              </div>

              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <label className="block text-xs font-bold text-gray-700 uppercase tracking-wider">Subject / Re:</label>
                  <div className="flex items-center gap-1">
                    <button
                      type="button"
                      onClick={() => insertFormat('subject', 'bold')}
                      className="p-1 text-gray-500 hover:text-purple-600 hover:bg-gray-100 rounded text-xs font-bold border border-gray-200 px-2 py-0.5 shadow-sm"
                      title="Bold selection"
                    >
                      B
                    </button>
                    <button
                      type="button"
                      onClick={() => insertFormat('subject', 'italic')}
                      className="p-1 text-gray-500 hover:text-purple-600 hover:bg-gray-100 rounded text-xs italic border border-gray-200 px-2 py-0.5 shadow-sm"
                      title="Italic selection"
                    >
                      I
                    </button>
                  </div>
                </div>
                <input
                  type="text"
                  name="subject"
                  value={state.subject}
                  onChange={handleInputChange}
                  className="w-full text-sm border border-gray-200 rounded-lg p-2.5 font-semibold focus:border-purple-500"
                />
              </div>

              <div className="border-t border-gray-100 pt-4 space-y-3.5">
                <h3 className="text-xs font-bold text-gray-400 uppercase tracking-wider">Recipient Details</h3>

                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Recipient Name</label>
                  <input
                    type="text"
                    name="recipientName"
                    value={state.recipientName}
                    onChange={handleInputChange}
                    className="w-full text-sm border border-gray-200 rounded-lg p-2 focus:border-purple-500"
                  />
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">Title / Role</label>
                    <input
                      type="text"
                      name="recipientTitle"
                      value={state.recipientTitle}
                      onChange={handleInputChange}
                      className="w-full text-sm border border-gray-200 rounded-lg p-2 focus:border-purple-500"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">Company / Organization</label>
                    <input
                      type="text"
                      name="recipientOrg"
                      value={state.recipientOrg}
                      onChange={handleInputChange}
                      className="w-full text-sm border border-gray-200 rounded-lg p-2 focus:border-purple-500"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Address</label>
                  <input
                    type="text"
                    name="recipientAddress"
                    value={state.recipientAddress}
                    onChange={handleInputChange}
                    className="w-full text-sm border border-gray-200 rounded-lg p-2 focus:border-purple-500"
                  />
                </div>
              </div>
            </div>
          )}

          {/* TAB 3: LETTER BODY */}
          {activeTab === 'body' && (
            <div className="space-y-4 animate-fadeIn h-full flex flex-col">
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <label className="block text-xs font-bold text-gray-700 uppercase tracking-wider">Letter Contents</label>
                  <div className="flex items-center gap-1">
                    <button
                      type="button"
                      onClick={() => insertFormat('letterBody', 'bold')}
                      className="p-1 text-gray-500 hover:text-purple-600 hover:bg-gray-100 rounded text-xs font-bold border border-gray-200 px-2 py-0.5 shadow-sm"
                      title="Bold selection (**bold**)"
                    >
                      B
                    </button>
                    <button
                      type="button"
                      onClick={() => insertFormat('letterBody', 'italic')}
                      className="p-1 text-gray-500 hover:text-purple-600 hover:bg-gray-100 rounded text-xs italic border border-gray-200 px-2 py-0.5 shadow-sm"
                      title="Italic selection (*italic*)"
                    >
                      I
                    </button>
                  </div>
                </div>
                <p className="text-[10px] text-gray-400 mb-2">
                  Format tips: Wrap words with <code className="bg-gray-100 px-1 py-0.2 rounded font-mono">**bold**</code> or <code className="bg-gray-100 px-1 py-0.2 rounded font-mono">*italic*</code>.
                </p>
                <textarea
                  name="letterBody"
                  value={state.letterBody}
                  onChange={handleInputChange}
                  rows={14}
                  className="w-full text-sm border border-gray-200 rounded-lg p-3 focus:border-purple-500 focus:ring-1 focus:ring-purple-500 font-sans leading-relaxed h-[calc(100vh-320px)] min-h-[300px]"
                />
              </div>
            </div>
          )}

          {/* TAB 4: SIGNATURE & FOOTER */}
          {activeTab === 'signature' && (
            <div className="space-y-4 animate-fadeIn">
              <div>
                <h3 className="text-xs font-bold text-gray-700 uppercase tracking-wider mb-3">Signatory</h3>

                <div className="grid grid-cols-2 gap-3 mb-3">
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">Name</label>
                    <input
                      type="text"
                      name="signatoryName"
                      value={state.signatoryName}
                      onChange={handleInputChange}
                      className="w-full text-sm border border-gray-200 rounded-lg p-2 focus:border-purple-500"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">Title</label>
                    <input
                      type="text"
                      name="signatoryTitle"
                      value={state.signatoryTitle}
                      onChange={handleInputChange}
                      className="w-full text-sm border border-gray-200 rounded-lg p-2 focus:border-purple-500"
                    />
                  </div>
                </div>

                <div className="mb-4">
                  <label className="block text-xs font-medium text-gray-600 mb-1.5">Signature Format</label>
                  <div className="flex gap-4">
                    <label className="flex items-center gap-1.5 text-xs font-semibold text-gray-700 cursor-pointer">
                      <input
                        type="radio"
                        name="signatureType"
                        checked={state.signatureType === 'typed'}
                        onChange={() => setState(prev => ({ ...prev, signatureType: 'typed' }))}
                        className="text-purple-600 focus:ring-purple-500"
                      />
                      Script Font
                    </label>
                    <label className="flex items-center gap-1.5 text-xs font-semibold text-gray-700 cursor-pointer">
                      <input
                        type="radio"
                        name="signatureType"
                        checked={state.signatureType === 'uploaded'}
                        onChange={() => setState(prev => ({ ...prev, signatureType: 'uploaded' }))}
                        className="text-purple-600 focus:ring-purple-500"
                      />
                      Upload Image
                    </label>
                  </div>
                </div>

                {state.signatureType === 'typed' ? (
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">Type Signature</label>
                    <input
                      type="text"
                      name="signatureText"
                      value={state.signatureText}
                      onChange={handleInputChange}
                      className="w-full text-sm border border-gray-200 rounded-lg p-2.5 focus:border-purple-500 font-serif"
                    />
                  </div>
                ) : (
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1.5">Upload Signature Image</label>
                    <div className="flex items-center gap-3">
                      {state.signatureUrl && (
                        <img src={state.signatureUrl} alt="Signature" className="h-10 w-24 object-contain bg-gray-50 border border-gray-100 p-1 rounded-lg" />
                      )}
                      <input
                        type="file"
                        ref={sigInputRef}
                        onChange={handleSignatureUpload}
                        accept="image/*"
                        className="hidden"
                      />
                      <button
                        type="button"
                        onClick={() => sigInputRef.current?.click()}
                        className="text-xs bg-gray-100 hover:bg-gray-200 font-semibold py-2 px-3 border border-gray-200 rounded-lg transition"
                      >
                        Select Image
                      </button>
                    </div>
                  </div>
                )}
              </div>

              <div className="border-t border-gray-100 pt-4">
                <label className="block text-xs font-bold text-gray-700 uppercase tracking-wider mb-1.5">Footer Text / Legal Disclaimer</label>
                <input
                  type="text"
                  name="footerText"
                  value={state.footerText}
                  onChange={handleInputChange}
                  className="w-full text-sm border border-gray-200 rounded-lg p-2.5 focus:border-purple-500"
                />
              </div>
            </div>
          )}

          {/* TAB 5: TEMPLATES & STYLE */}
          {activeTab === 'style' && (
            <div className="space-y-4 animate-fadeIn">
              <div>
                <label className="block text-xs font-bold text-gray-700 uppercase tracking-wider mb-2">Preset Templates</label>
                <div className="grid grid-cols-2 gap-3">
                  {(Object.keys(THEME_PRESETS) as ThemeId[]).map(themeId => (
                    <button
                      key={themeId}
                      type="button"
                      onClick={() => selectTheme(themeId)}
                      className={`flex flex-col text-left p-3 border rounded-lg transition-all ${
                        state.theme === themeId
                          ? 'border-purple-650 bg-purple-50/50 shadow-sm ring-1 ring-purple-655'
                          : 'border-gray-200 hover:bg-gray-50'
                      }`}
                    >
                      <span className="text-xs font-bold text-gray-900">{THEME_PRESETS[themeId].name}</span>
                      <span className="text-[10px] text-gray-500 mt-1 capitalize">{themeId.replace('_', ' ')}</span>
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="block text-xs font-bold text-gray-700 uppercase tracking-wider mb-1.5">Accent Color</label>
                <div className="flex items-center gap-3">
                  <input
                    type="color"
                    name="accentColor"
                    value={state.accentColor}
                    onChange={handleInputChange}
                    className="w-10 h-10 border border-gray-200 rounded-md cursor-pointer p-0.5"
                  />
                  <input
                    type="text"
                    name="accentColor"
                    value={state.accentColor}
                    onChange={handleInputChange}
                    placeholder="#HEX"
                    className="w-28 text-sm border border-gray-200 rounded-lg p-2 focus:border-purple-500 uppercase"
                  />
                </div>
              </div>
            </div>
          )}

          {/* TAB 6: HISTORY */}
          {activeTab === 'history' && (
            <div className="space-y-4 animate-fadeIn">
              <div className="flex items-center justify-between mb-2">
                <h3 className="text-xs font-bold text-gray-700 uppercase tracking-wider">Saved Letterheads</h3>
                <span className="text-[10px] text-gray-400 bg-gray-150 px-2 py-0.5 rounded-full font-semibold">
                  {historyData?.letterheads?.length || 0} items
                </span>
              </div>

              {historyLoading ? (
                <div className="flex flex-col items-center justify-center py-12 text-gray-400 gap-2">
                  <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-purple-600"></div>
                  <span className="text-xs">Loading history...</span>
                </div>
              ) : historyError ? (
                <div className="text-center py-8 text-red-500 text-xs">
                  Error loading history: {historyError.message}
                </div>
              ) : !historyData?.letterheads || historyData.letterheads.length === 0 ? (
                <div className="text-center py-12 text-gray-400 text-xs border border-dashed border-gray-200 rounded-xl">
                  No saved letterheads found. Save your current letterhead to see it here!
                </div>
              ) : (
                <div className="space-y-2.5 max-h-[calc(100vh-280px)] overflow-y-auto pr-1">
                  {historyData.letterheads.map((lh: any) => (
                    <div
                      key={lh.id}
                      className={`group border rounded-xl p-3.5 transition-all text-left relative flex flex-col gap-1.5 cursor-pointer ${
                        loadedId === lh.id
                          ? 'border-purple-600 bg-purple-50/20 shadow-sm ring-1 ring-purple-600'
                          : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50/50'
                      }`}
                      onClick={() => loadLetterhead(lh)}
                    >
                      <div className="flex items-start justify-between">
                        <h4 className="text-sm font-bold text-gray-900 line-clamp-1 pr-6">{lh.title}</h4>
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDeleteClick(lh.id, lh.title);
                          }}
                          className="text-gray-450 hover:text-red-600 p-1 rounded-lg transition absolute right-2.5 top-2.5 md:opacity-0 group-hover:opacity-100 focus:opacity-100"
                          title="Delete saved letter"
                        >
                          <TrashIcon className="w-4.5 h-4.5" />
                        </button>
                      </div>

                      <div className="text-[11px] text-gray-550 flex flex-col gap-0.5">
                        {lh.subject && <div className="line-clamp-1"><span className="font-semibold">Subj:</span> {lh.subject.replace(/\*\*|\*|_/g, '')}</div>}
                        {lh.recipient_name && <div><span className="font-semibold">To:</span> {lh.recipient_name}</div>}
                        <div className="text-[10px] text-gray-400 mt-1 flex justify-between items-center">
                          <span>Date: {lh.date || 'N/A'}</span>
                          <span>Updated: {new Date(lh.updated_at).toLocaleDateString()}</span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Right panel: A4 Paper Preview */}
      <div className="flex-1 bg-gray-100 flex justify-center items-start overflow-y-auto p-4 md:p-8 min-h-[calc(100vh-64px)] print-wrapper">
        <div className="w-[210mm] min-h-[297mm] bg-white shadow-xl border border-gray-200/50 p-[20mm] box-border relative flex flex-col justify-between letterhead-sheet select-text">
          
          {/* A4 Sheet Body - Flows naturally without forcing the signature to the bottom */}
          <div className="flex flex-col">
            
            {/* Header Layout based on theme */}
            <div className={`flex flex-col md:flex-row pb-6 mb-8 items-start ${currentTheme.borderStyle} ${
              currentTheme.align === 'between' ? 'justify-between' :
              currentTheme.align === 'center' ? 'items-center text-center flex-col' :
              currentTheme.align === 'right' ? 'items-end text-right flex-col' : 'justify-start'
            }`}>
              
              {/* Logo / Left Block */}
              {state.logoUrl && (
                <div className="mb-4 md:mb-0 flex items-center justify-center">
                  <img src={state.logoUrl} alt="Logo" className="h-16 w-auto object-contain max-w-[150px]" />
                </div>
              )}

              {/* Company Info Block */}
              <div className={`mt-2 md:mt-0 ${
                currentTheme.align === 'between' ? 'text-right' :
                currentTheme.align === 'center' ? 'text-center' :
                currentTheme.align === 'right' ? 'text-right' : 'text-left ml-4'
              }`}>
                <h1 className={`${currentTheme.fontHeader} text-lg md:text-xl tracking-normal`} style={{ color: state.accentColor }}>
                  {renderFormattedText(state.companyName)}
                </h1>
                {state.tagline && (
                  <p className="text-xs italic text-gray-550 font-medium mt-0.5">{renderFormattedText(state.tagline)}</p>
                )}
                
                {/* Contact grid block */}
                <div className="mt-3 text-[10px] text-gray-500 flex flex-wrap gap-x-3 gap-y-1 justify-end">
                  {state.address && (
                    <span className="flex items-center gap-1">
                      <MapPinIcon className="w-3 h-3 flex-shrink-0" style={{ color: state.accentColor }} />
                      {renderFormattedText(state.address)}
                    </span>
                  )}
                  {state.phone && (
                    <span className="flex items-center gap-1">
                      <PhoneIcon className="w-3 h-3 flex-shrink-0" style={{ color: state.accentColor }} />
                      {renderFormattedText(state.phone)}
                    </span>
                  )}
                  {state.email && (
                    <span className="flex items-center gap-1">
                      <EnvelopeIcon className="w-3 h-3 flex-shrink-0" style={{ color: state.accentColor }} />
                      {renderFormattedText(state.email)}
                    </span>
                  )}
                  {state.website && (
                    <span className="flex items-center gap-1">
                      <GlobeAltIcon className="w-3 h-3 flex-shrink-0" style={{ color: state.accentColor }} />
                      {renderFormattedText(state.website)}
                    </span>
                  )}
                </div>
              </div>
            </div>

            {/* Document Metadata (Date, Ref) */}
            <div className="flex justify-between items-start text-xs text-gray-500 mb-6 font-medium">
              {state.refNo ? (
                <div>
                  <span className="font-semibold text-gray-600">Ref:</span> {renderFormattedText(state.refNo)}
                </div>
              ) : <div />}
              <div>{renderFormattedText(state.date)}</div>
            </div>

            {/* Recipient Block */}
            {(state.recipientName || state.recipientTitle || state.recipientOrg || state.recipientAddress) && (
              <div className="mb-6 text-xs text-gray-700 leading-relaxed font-medium">
                {state.recipientName && <p className="font-bold text-gray-900 text-sm">{renderFormattedText(state.recipientName)}</p>}
                {state.recipientTitle && <p className="text-gray-650">{renderFormattedText(state.recipientTitle)}</p>}
                {state.recipientOrg && <p className="font-semibold text-gray-750">{renderFormattedText(state.recipientOrg)}</p>}
                {state.recipientAddress && <p className="text-gray-550">{renderFormattedText(state.recipientAddress)}</p>}
              </div>
            )}

            {/* Subject Line */}
            {state.subject && (
              <div className="mb-6 border-l-2 pl-3 py-0.5 text-sm font-bold text-gray-900" style={{ borderLeftColor: state.accentColor }}>
                SUBJECT: {renderFormattedText(state.subject.toUpperCase())}
              </div>
            )}

            {/* Letter Body */}
            <div className={`${currentTheme.fontBody} text-sm leading-relaxed whitespace-pre-line`}>
              {renderFormattedText(state.letterBody)}
            </div>

            {/* Signature Block - Placed right below letter body with underline indicator and zero labels */}
            <div className="mt-12 pb-2 page-break-avoid flex flex-col items-start select-none">
              <div className="relative w-56">
                {state.signatureType === 'typed' ? (
                  <div className="pl-2 pb-1.5 text-2xl h-9 flex items-end font-normal" style={{ fontFamily: "'Dancing Script', 'Great Vibes', cursive", color: state.accentColor }}>
                    {state.signatureText}
                  </div>
                ) : (
                  <div className="h-12 flex items-end mb-1 pl-2">
                    {state.signatureUrl ? (
                      <img src={state.signatureUrl} alt="Signature" className="h-12 w-auto object-contain" />
                    ) : (
                      <div className="h-8" />
                    )}
                  </div>
                )}
                {/* Physical Signature Line Indicator */}
                <div className="border-t border-gray-400 w-full my-1"></div>
              </div>
              <div className="text-xs font-bold text-gray-900 mt-1">{renderFormattedText(state.signatoryName)}</div>
              <div className="text-[11px] text-gray-550 font-medium">{renderFormattedText(state.signatoryTitle)}</div>
            </div>

          </div>

          {/* Footer Text */}
          {state.footerText && (
            <div className="border-t border-gray-100 pt-4 mt-8 text-center text-[10px] text-gray-400 font-medium">
              {renderFormattedText(state.footerText)}
            </div>
          )}

        </div>
      </div>

      {/* Save Modal */}
      {isSaveModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 animate-fadeIn no-print">
          <div className="bg-white rounded-xl shadow-xl max-w-md w-full p-6 space-y-4 border border-gray-100 animate-slideUp">
            <div>
              <h3 className="text-lg font-bold text-gray-900">Save Letterhead</h3>
              <p className="text-xs text-gray-550 mt-0.5">Provide a title to save this letterhead to history.</p>
            </div>

            <div>
              <label className="block text-xs font-semibold text-gray-700 uppercase tracking-wider mb-1">Document Title</label>
              <input
                type="text"
                value={saveTitle}
                onChange={(e) => setSaveTitle(e.target.value)}
                placeholder="e.g., Summer Camp Announcement July 2026"
                className="w-full text-sm border border-gray-300 rounded-lg p-2.5 focus:ring-1 focus:ring-purple-500 focus:border-purple-500 font-semibold"
                autoFocus
              />
            </div>

            {loadedId && (
              <div className="flex gap-4 p-2.5 bg-purple-50/50 rounded-lg border border-purple-100/50 text-[11px] text-purple-800">
                <label className="flex items-center gap-1.5 cursor-pointer font-semibold">
                  <input
                    type="radio"
                    name="saveMode"
                    checked={!saveAsNew}
                    onChange={() => setSaveAsNew(false)}
                    className="text-purple-600 focus:ring-purple-500"
                  />
                  Overwrite existing
                </label>
                <label className="flex items-center gap-1.5 cursor-pointer font-semibold">
                  <input
                    type="radio"
                    name="saveMode"
                    checked={saveAsNew}
                    onChange={() => setSaveAsNew(true)}
                    className="text-purple-600 focus:ring-purple-500"
                  />
                  Save as new copy
                </label>
              </div>
            )}

            <div className="flex gap-2 justify-end pt-2">
              <button
                type="button"
                onClick={() => setIsSaveModalOpen(false)}
                className="px-4 py-2 text-xs font-semibold text-gray-555 hover:bg-gray-100 rounded-lg transition"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={!saveTitle.trim()}
                onClick={handleSaveSubmit}
                className="px-4 py-2 text-xs font-semibold bg-purple-600 hover:bg-purple-700 text-white rounded-lg transition shadow-sm disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Save Letterhead
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
