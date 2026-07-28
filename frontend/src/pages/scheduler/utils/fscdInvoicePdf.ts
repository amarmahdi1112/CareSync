import jsPDF from 'jspdf';
import autoTable from 'jspdf-autotable';

interface FSCDEntry {
  date: string;
  startTime: string;
  endTime: string;
  hours: number;
}

interface FSCDInvoiceData {
  /**
   * Scheduler exports are based on planned attendance, never verified service delivery.
   * Keeping this as a required literal prevents this utility from silently producing an
   * official-looking invoice from projected rows.
   */
  documentStatus: 'projected-draft';

  // Provider Info
  providerName: string;
  providerPhone: string;
  providerEmail: string;
  providerAddress: string;
  providerCity: string;
  providerPostalCode: string;
  
  // Invoice Info
  invoiceMonth: string;
  invoiceYear: number;
  invoiceNumber: string;
  fscdNumber: string;
  businessPartnerNumber: string;
  
  // Child Info
  childName: string;
  
  // Entries
  entries: FSCDEntry[];
  
  // Rate
  hourlyRate: number;
  
  // Service type
  serviceType: string;
}

function formatDateForInvoice(dateStr: string): string {
  const date = new Date(`${dateStr}T12:00:00`);
  const day = date.getDate();
  const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  return `${day}-${monthNames[date.getMonth()]}`;
}

function formatTimeForInvoice(time: string): string {
  if (!time) return '';
  const [h, m] = time.split(':').map(Number);
  const period = h >= 12 ? 'PM' : 'AM';
  const hour = h > 12 ? h - 12 : h === 0 ? 12 : h;
  return `${hour}:${m.toString().padStart(2, '0')} ${period}`;
}

function buildFSCDInvoiceDoc(data: FSCDInvoiceData): jsPDF {
  const doc = new jsPDF({
    orientation: 'portrait',
    unit: 'mm',
    format: 'letter'
  });

  const pageWidth = doc.internal.pageSize.getWidth();
  const pageHeight = doc.internal.pageSize.getHeight();
  const margin = 15;
  let y = 15;

  // ===== HEADER - Provider Info =====
  doc.setFontSize(14);
  doc.setFont('helvetica', 'bold');
  doc.text(data.providerName, margin, y);
  
  y += 5;
  doc.setFontSize(9);
  doc.setFont('helvetica', 'normal');
  doc.text(data.providerPhone, margin, y);
  
  y += 4;
  doc.text(data.providerEmail, margin, y);
  
  y += 4;
  doc.text(data.providerAddress, margin, y);
  
  y += 4;
  doc.text(`${data.providerCity}`, margin, y);
  
  y += 4;
  doc.text(data.providerPostalCode, margin, y);

  // ===== Invoice Month Header =====
  y += 8;
  doc.setFontSize(10);
  doc.setFont('helvetica', 'bold');
  doc.text('Invoice for the month of:', margin, y);
  doc.setFont('helvetica', 'normal');
  doc.setTextColor(0, 128, 0); // Green
  doc.text(`${data.invoiceMonth}`, margin + 45, y);
  doc.text(`${data.invoiceYear}`, margin + 60, y);
  doc.setTextColor(0, 0, 0); // Back to black

  // ===== Invoice Details Box =====
  y += 5;
  
  // Row 1: Invoice # and FSCD #
  doc.setFillColor(198, 224, 180); // Light green
  doc.rect(margin, y, 60, 6, 'F');
  doc.rect(pageWidth / 2, y, 60, 6, 'F');
  
  doc.setFontSize(9);
  doc.setFont('helvetica', 'bold');
  doc.text('Invoice #:', margin + 2, y + 4);
  doc.text('FSCD #:', pageWidth / 2 + 2, y + 4);
  
  doc.setFont('helvetica', 'normal');
  doc.text(data.invoiceNumber, margin + 25, y + 4);
  doc.text(data.fscdNumber, pageWidth / 2 + 25, y + 4);
  
  // Row 2: Business Partner # and Child Name
  y += 6;
  doc.setFillColor(198, 224, 180);
  doc.rect(margin, y, 60, 6, 'F');
  doc.rect(pageWidth / 2, y, 60, 6, 'F');
  
  doc.setFont('helvetica', 'bold');
  doc.text('Business Partner #:', margin + 2, y + 4);
  doc.text('Child Name:', pageWidth / 2 + 2, y + 4);
  
  doc.setFont('helvetica', 'normal');
  doc.setTextColor(0, 128, 0);
  doc.text(data.businessPartnerNumber, margin + 35, y + 4);
  doc.text(data.childName, pageWidth / 2 + 28, y + 4);
  doc.setTextColor(0, 0, 0);

  // ===== Service Title =====
  y += 10;
  doc.setFillColor(255, 255, 153); // Yellow
  doc.rect(margin, y, pageWidth - 2 * margin, 6, 'F');
  doc.setFont('helvetica', 'bold');
  doc.setFontSize(10);
  doc.text('AIDE IN CHILD CARE FACILITY SERVICES PROVIDED:', margin + 2, y + 4);

  // ===== Table =====
  y += 8;
  
  // Calculate totals
  const totalHours = data.entries.reduce((sum, e) => sum + e.hours, 0);
  const totalCost = totalHours * data.hourlyRate;
  
  // Prepare table data
  const tableData: (string | { content: string; colSpan?: number; styles?: Record<string, unknown> })[][] = data.entries.map(entry => [
    formatDateForInvoice(entry.date),
    formatDateForInvoice(entry.date),
    data.serviceType,
    formatTimeForInvoice(entry.startTime),
    formatTimeForInvoice(entry.endTime),
    entry.hours.toFixed(1),
    `$ ${data.hourlyRate.toFixed(1)}`,
    '$',
    (entry.hours * data.hourlyRate).toFixed(2)
  ]);

  // Add totals row to body (more reliable than foot)
  tableData.push([
    { content: 'TOTALS', colSpan: 5, styles: { fillColor: [198, 224, 180], fontStyle: 'bold', halign: 'left' } },
    { content: totalHours.toFixed(0), styles: { halign: 'center' } },
    { content: '', styles: {} },
    { content: '$', styles: { halign: 'center' } },
    { content: totalCost.toFixed(2), styles: { halign: 'center' } }
  ]);

  autoTable(doc, {
    startY: y,
    head: [[
      'Start\nDate',
      'End Date',
      'Service',
      'Start Time',
      'End Time',
      'Total Hours',
      'Rate per\nHour',
      '',
      'Total Cost'
    ]],
    body: tableData,
    theme: 'grid',
    styles: {
      fontSize: 8,
      cellPadding: 1.5,
      lineColor: [0, 0, 0],
      lineWidth: 0.1,
    },
    headStyles: {
      fillColor: [198, 224, 180],
      textColor: [0, 0, 0],
      fontStyle: 'bold',
      halign: 'center',
      valign: 'middle',
    },
    bodyStyles: {
      halign: 'center',
    },
    columnStyles: {
      0: { cellWidth: 18 },
      1: { cellWidth: 18 },
      2: { cellWidth: 30 },
      3: { cellWidth: 22 },
      4: { cellWidth: 22 },
      5: { cellWidth: 20 },
      6: { cellWidth: 20 },
      7: { cellWidth: 8 },
      8: { cellWidth: 22 },
    },
    margin: { left: margin, right: margin },
  });

  // ===== PAGE 2 - Signatures =====
  doc.addPage();
  y = 20;

  // Divider line
  doc.setDrawColor(0);
  doc.setLineWidth(0.5);
  doc.line(margin, y, pageWidth - margin, y);

  // Additional Comments
  y += 8;
  doc.setFontSize(10);
  doc.setFont('helvetica', 'bold');
  doc.text('Additional Comments:', margin, y);
  
  y += 3;
  doc.setDrawColor(0);
  doc.setLineWidth(0.2);
  doc.rect(margin, y, pageWidth - 2 * margin, 20);
  
  // Parent/Guardian Section
  y += 28;
  doc.setFont('helvetica', 'bold');
  doc.setFontSize(10);
  doc.text('PARENT/GUARDIAN:', margin, y);
  doc.setLineWidth(0.5);
  doc.line(margin, y + 1, margin + 38, y + 1);

  y += 5;
  doc.setFont('helvetica', 'normal');
  doc.setFontSize(8);
  const parentText = `I confirm that my child care facility (service provider) has provided the Aide in Child Care Facility services to my child as outlined above. I confirm that my child was not receiving PUF or other services at the same time that the Aide in Child Care Facility services were being provided to my child. I acknowledge my responsibility as the employer of my chosen service provider. The director, upon request of the Guardian, agrees to provide payment directly to the service provider who is a service provider chosen by the Guardian, solely for the purposes of administrative ease and efficiency.`;
  
  const splitParentText = doc.splitTextToSize(parentText, pageWidth - 2 * margin);
  doc.text(splitParentText, margin, y);

  y += splitParentText.length * 3.5 + 5;
  
  // Parent signature line
  // Projected schedules cannot prove that service was delivered. Stored signatures are
  // therefore deliberately excluded from this scheduler-generated draft.
  doc.setFontSize(7);
  doc.setFont('helvetica', 'italic');
  doc.setTextColor(180, 30, 30);
  doc.text('Signature intentionally omitted from projected draft.', margin, y + 2);
  doc.setTextColor(0, 0, 0);
  doc.setFont('helvetica', 'normal');
  
  doc.setFillColor(255, 255, 153);
  doc.rect(margin, y + 5, 80, 6, 'F');
  doc.rect(pageWidth - margin - 50, y + 5, 50, 6, 'F');
  
  doc.setFontSize(8);
  doc.text('Parent/Guardian Signature', margin + 20, y + 9);
  doc.text('Date', pageWidth - margin - 30, y + 9);
  
  // Director Section
  y += 20;
  doc.setFont('helvetica', 'bold');
  doc.setFontSize(10);
  doc.text('CHILD CARE FACILITY DIRECTOR OR ADMINISTRATIVE DESIGNATE:', margin, y);
  doc.setLineWidth(0.5);
  doc.line(margin, y + 1, margin + 115, y + 1);

  y += 5;
  doc.setFont('helvetica', 'normal');
  doc.setFontSize(8);
  const directorText = `I confirm that the Aide in Child Care Facility services outlined above were provided to the above-named child only. I acknowledge that the FSCD funded Aide cannot be used to meet ratio numbers. I confirm that the above-named child was not receiving PUF or other services at the same time as the Aide in Child Care Facility services were being provided to the child. I confirm that the above services have been provided and accept responsibility to pay the Aide directly. Confirmation that the service has been received must be provided to the director by the guardian prior to payment.`;
  
  const splitDirectorText = doc.splitTextToSize(directorText, pageWidth - 2 * margin);
  doc.text(splitDirectorText, margin, y);

  y += splitDirectorText.length * 3.5 + 5;
  
  // Director signature line
  doc.setFontSize(7);
  doc.setFont('helvetica', 'italic');
  doc.setTextColor(180, 30, 30);
  doc.text('Signature intentionally omitted from projected draft.', margin, y + 2);
  doc.setTextColor(0, 0, 0);
  doc.setFont('helvetica', 'normal');
  
  doc.setFillColor(255, 255, 153);
  doc.rect(margin, y + 5, 80, 6, 'F');
  doc.rect(pageWidth - margin - 50, y + 5, 50, 6, 'F');
  
  doc.setFontSize(8);
  doc.text('Director Signature', margin + 25, y + 9);
  doc.text('Date', pageWidth - margin - 30, y + 9);
  
  // Notice box
  y += 20;
  doc.setFillColor(255, 255, 153);
  doc.rect(margin, y, pageWidth - 2 * margin, 20, 'F');
  doc.setDrawColor(0);
  doc.rect(margin, y, pageWidth - 2 * margin, 20);
  
  y += 5;
  doc.setFont('helvetica', 'bold');
  doc.setFontSize(9);
  doc.text('Child Care Facility Directors or Administrative Designate:', margin + 2, y);
  
  y += 4;
  doc.setFont('helvetica', 'normal');
  doc.setFontSize(8);
  const noticeText = `Please note that you may be asked to provide additional supporting documentation or information if a clarification or discrepancy should arise.\nAdditional documentation may include the employee time sheet or the child attendance record.`;
  const splitNotice = doc.splitTextToSize(noticeText, pageWidth - 2 * margin - 4);
  doc.text(splitNotice, margin + 2, y);

  // Every page must remain identifiable if it is printed, split, or removed from a ZIP.
  for (let page = 1; page <= doc.getNumberOfPages(); page += 1) {
    doc.setPage(page);
    doc.setFont('helvetica', 'bold');
    doc.setTextColor(245, 190, 190);
    doc.setFontSize(30);
    doc.text('DRAFT - PROJECTED', pageWidth / 2, pageHeight / 2, {
      align: 'center',
      angle: 45,
    });
    doc.setTextColor(185, 28, 28);
    doc.setFontSize(8);
    doc.text(
      'PROJECTED SCHEDULE - NOT PROOF OF ATTENDANCE OR SERVICE DELIVERY',
      pageWidth / 2,
      7,
      { align: 'center' },
    );
    doc.setFont('helvetica', 'normal');
    doc.setFontSize(7);
    doc.text(
      'Draft generated from planned scheduler data. Reconcile with actual attendance before official use.',
      pageWidth / 2,
      pageHeight - 5,
      { align: 'center' },
    );
    doc.setTextColor(0, 0, 0);
  }

  return doc;
}

export function generateFSCDInvoicePDF(data: FSCDInvoiceData): void {
  const doc = buildFSCDInvoiceDoc(data);
  // Save PDF
  const safeName = data.childName.replace(/[^a-zA-Z0-9]/g, '_');
  doc.save(`DRAFT_PROJECTED_FSCD_${safeName}_${data.invoiceMonth}${data.invoiceYear}.pdf`);
}

export function generateFSCDInvoiceBlob(data: FSCDInvoiceData): Blob {
  const doc = buildFSCDInvoiceDoc(data);
  return doc.output('blob');
}

export type { FSCDInvoiceData, FSCDEntry };
