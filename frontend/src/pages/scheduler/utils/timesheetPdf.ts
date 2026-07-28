/**
 * PDF Generation utility for printing children's attendance timesheets
 * 
 * EXACT PAPER LAYOUT (A4 PORTRAIT - FULL PAGE):
 * | Name       | (blank) | MON     | TUES    | WEDS    | THURS   | FRI     | Signature |
 */

import jsPDF from 'jspdf';

export interface ChildAttendanceData {
    name: string;
    dateOfBirth: string;
    entries: {
        date: string;
        startTime1?: string;
        endTime1?: string;
        startTime2?: string;
        endTime2?: string;
    }[];
}

interface WeekData {
    weekStart: string;
    days: {
        dayName: 'MON' | 'TUES' | 'WEDS' | 'THURS' | 'FRI';
        date: string;
        startTime1?: string;
        endTime1?: string;
        startTime2?: string;
        endTime2?: string;
    }[];
}

const DAY_NAMES: readonly string[] = ['SUN', 'MON', 'TUES', 'WEDS', 'THURS', 'FRI', 'SAT'];
const WEEKDAYS: readonly ('MON' | 'TUES' | 'WEDS' | 'THURS' | 'FRI')[] = ['MON', 'TUES', 'WEDS', 'THURS', 'FRI'];

function groupEntriesByWeek(entries: ChildAttendanceData['entries']): WeekData[] {
    const weeks = new Map<string, WeekData>();

    entries.forEach(entry => {
        const date = new Date(`${entry.date}T12:00:00`);
        const dayOfWeek = date.getDay();
        if (dayOfWeek === 0 || dayOfWeek === 6) return;

        const monday = new Date(date);
        monday.setDate(date.getDate() - (dayOfWeek - 1));
        const weekKey = monday.toISOString().split('T')[0];

        if (!weeks.has(weekKey)) {
            weeks.set(weekKey, { weekStart: weekKey, days: [] });
        }

        weeks.get(weekKey)!.days.push({
            dayName: DAY_NAMES[dayOfWeek] as 'MON' | 'TUES' | 'WEDS' | 'THURS' | 'FRI',
            date: entry.date,
            startTime1: entry.startTime1,
            endTime1: entry.endTime1,
            startTime2: entry.startTime2,
            endTime2: entry.endTime2,
        });
    });

    return Array.from(weeks.values()).sort((a, b) => a.weekStart.localeCompare(b.weekStart));
}

const formatTime = (time?: string): string => {
    if (!time) return '';
    const [h, m] = time.split(':').map(Number);
    const hour = h > 12 ? h - 12 : h === 0 ? 12 : h;
    return `${hour}:${m.toString().padStart(2, '0')}`;
};

const calcHours = (start?: string, end?: string): number => {
    if (!start || !end) return 0;
    const [sh, sm] = start.split(':').map(Number);
    const [eh, em] = end.split(':').map(Number);
    return ((eh * 60 + em) - (sh * 60 + sm)) / 60;
};

// Auto-shrink text to fit in column width
function drawFittedText(
    doc: jsPDF,
    text: string,
    x: number,
    y: number,
    maxWidth: number,
    maxFontSize: number,
    minFontSize: number = 5,
    fontStyle: 'normal' | 'bold' = 'normal'
): void {
    doc.setFont('helvetica', fontStyle);
    let fontSize = maxFontSize;
    doc.setFontSize(fontSize);

    // Measure text width and shrink font until it fits
    while (doc.getTextWidth(text) > maxWidth - 3 && fontSize > minFontSize) {
        fontSize -= 0.5;
        doc.setFontSize(fontSize);
    }

    doc.text(text, x, y);
}

function buildTimesheetDoc(
    children: ChildAttendanceData[],
    monthYear: string
): jsPDF {
    const doc = new jsPDF({
        orientation: 'portrait',
        unit: 'mm',
        format: 'a4'
    });

    const pageWidth = doc.internal.pageSize.getWidth();   // 210mm
    const pageHeight = doc.internal.pageSize.getHeight(); // 297mm
    const margin = 12;
    const tableWidth = pageWidth - margin * 2;

    // Column widths - proportional to table width
    const cols = {
        name: tableWidth * 0.20,      // 20%
        indicator: tableWidth * 0.06, // 6%
        day: tableWidth * 0.115,      // 11.5% each x 5 = 57.5%
        signature: tableWidth * 0.165 // 16.5%
    };

    let isFirstPage = true;

    children.forEach(child => {
        if (!isFirstPage) {
            doc.addPage();
        }
        isFirstPage = false;

        const weeks = groupEntriesByWeek(child.entries);
        const numWeeks = weeks.length || 1;

        // Calculate available space and row heights dynamically
        const headerY = 20;
        const tableTop = 28;
        const grandTotalHeight = 12;
        const footerSpace = 10;
        const availableHeight = pageHeight - tableTop - grandTotalHeight - footerSpace;

        // Each week has 6 rows, plus 1 header row
        const totalRows = numWeeks * 6 + 1;
        const rowHeight = Math.min(availableHeight / totalRows, 12); // Max 12mm per row
        const headerHeight = rowHeight + 1;

        // Font sizes based on row height
        const titleFontSize = 12;
        const headerFontSize = Math.max(9, rowHeight * 0.9);
        const bodyFontSize = Math.max(8, rowHeight * 0.85);
        const labelFontSize = Math.max(7, rowHeight * 0.75);

        // === HEADER ===
        doc.setFontSize(titleFontSize);
        doc.setFont('helvetica', 'bold');
        doc.text('Direct Childcare Hours: Parents Please Initial and Sign', margin, headerY);

        doc.setFontSize(10);
        doc.text(monthYear, pageWidth - margin - 45, headerY);

        // === TABLE HEADER ===
        let y = tableTop;

        doc.setFillColor(240, 240, 240);
        doc.rect(margin, y, tableWidth, headerHeight, 'F');

        doc.setFont('helvetica', 'bold');
        doc.setFontSize(headerFontSize);

        let x = margin;
        doc.text('Name', x + 2, y + headerHeight * 0.65);
        x += cols.name;
        x += cols.indicator; // Blank column

        WEEKDAYS.forEach(day => {
            doc.text(day, x + cols.day / 2, y + headerHeight * 0.65, { align: 'center' });
            x += cols.day;
        });

        doc.text('Signature', x + 2, y + headerHeight * 0.65);

        doc.setDrawColor(0);
        doc.setLineWidth(0.4);
        doc.rect(margin, y, tableWidth, headerHeight);

        // Header column lines
        x = margin + cols.name;
        doc.line(x, y, x, y + headerHeight);
        x += cols.indicator;
        doc.line(x, y, x, y + headerHeight);
        WEEKDAYS.forEach(() => {
            x += cols.day;
            doc.line(x, y, x, y + headerHeight);
        });

        y += headerHeight;

        // === DRAW ALL WEEKS ===
        let grandTotal = 0;
        weeks.forEach((week) => {
            const blockTop = y;

            // ROW 1: Name + IN label + IN times (session 1)
            x = margin;
            // Use auto-shrink for names that might be too long
            drawFittedText(doc, child.name, x + 2, y + rowHeight * 0.65, cols.name, bodyFontSize, 5, 'bold');
            x += cols.name;

            // IN label for session 1 (first row)
            doc.setFont('helvetica', 'normal');
            doc.setFontSize(labelFontSize);
            doc.setTextColor(0, 150, 0);
            doc.text('IN', x + 2, y + rowHeight * 0.65);
            doc.setTextColor(0);
            x += cols.indicator;

            // Reset font for times
            doc.setFontSize(bodyFontSize);
            WEEKDAYS.forEach(dayName => {
                const dayData = week.days.find(d => d.dayName === dayName);
                if (dayData?.startTime1) {
                    doc.text(formatTime(dayData.startTime1), x + cols.day / 2, y + rowHeight * 0.65, { align: 'center' });
                }
                x += cols.day;
            });
            doc.setLineWidth(0.2);
            doc.rect(margin, y, tableWidth, rowHeight);
            y += rowHeight;

            // ROW 2: D.O.B + OUT times (session 1)
            x = margin;
            doc.setFontSize(labelFontSize);
            doc.text(`D.O.B: ${child.dateOfBirth || 'N/A'}`, x + 2, y + rowHeight * 0.65);
            x += cols.name;

            doc.setTextColor(200, 0, 0);
            doc.text('OUT', x + 2, y + rowHeight * 0.65);
            doc.setTextColor(0);
            x += cols.indicator;

            doc.setFontSize(bodyFontSize);
            WEEKDAYS.forEach(dayName => {
                const dayData = week.days.find(d => d.dayName === dayName);
                if (dayData?.endTime1) {
                    doc.text(formatTime(dayData.endTime1), x + cols.day / 2, y + rowHeight * 0.65, { align: 'center' });
                }
                x += cols.day;
            });
            doc.rect(margin, y, tableWidth, rowHeight);
            y += rowHeight;

            // ROW 3: IN times (session 2)
            x = margin + cols.name;
            doc.setTextColor(0, 150, 0);
            doc.setFontSize(labelFontSize);
            doc.text('IN', x + 2, y + rowHeight * 0.65);
            doc.setTextColor(0);
            x += cols.indicator;

            doc.setFontSize(bodyFontSize);
            WEEKDAYS.forEach(dayName => {
                const dayData = week.days.find(d => d.dayName === dayName);
                if (dayData?.startTime2) {
                    doc.text(formatTime(dayData.startTime2), x + cols.day / 2, y + rowHeight * 0.65, { align: 'center' });
                }
                x += cols.day;
            });
            doc.rect(margin, y, tableWidth, rowHeight);
            y += rowHeight;

            // ROW 4: OUT times (session 2)
            x = margin + cols.name;
            doc.setTextColor(200, 0, 0);
            doc.setFontSize(labelFontSize);
            doc.text('OUT', x + 2, y + rowHeight * 0.65);
            doc.setTextColor(0);
            x += cols.indicator;

            doc.setFontSize(bodyFontSize);
            WEEKDAYS.forEach(dayName => {
                const dayData = week.days.find(d => d.dayName === dayName);
                if (dayData?.endTime2) {
                    doc.text(formatTime(dayData.endTime2), x + cols.day / 2, y + rowHeight * 0.65, { align: 'center' });
                }
                x += cols.day;
            });
            doc.rect(margin, y, tableWidth, rowHeight);
            y += rowHeight;

            // ROW 5: INITIAL
            doc.setFontSize(labelFontSize);
            doc.text('INITIAL', margin + 2, y + rowHeight * 0.65);
            doc.rect(margin, y, tableWidth, rowHeight);
            y += rowHeight;

            // ROW 6: TOTAL — compute & display per-day and weekly totals
            doc.setFillColor(250, 250, 250);
            doc.rect(margin, y, tableWidth, rowHeight, 'F');
            doc.setFontSize(labelFontSize);
            doc.setFont('helvetica', 'bold');
            doc.text('TOTAL', margin + 2, y + rowHeight * 0.65);

            let weekTotal = 0;
            x = margin + cols.name + cols.indicator;
            doc.setFontSize(bodyFontSize);
            WEEKDAYS.forEach(dayName => {
                const dayData = week.days.find(d => d.dayName === dayName);
                if (dayData) {
                    const dayHours = calcHours(dayData.startTime1, dayData.endTime1)
                        + calcHours(dayData.startTime2, dayData.endTime2);
                    weekTotal += dayHours;
                    if (dayHours > 0) {
                        doc.text(dayHours.toFixed(1), x + cols.day / 2, y + rowHeight * 0.65, { align: 'center' });
                    }
                }
                x += cols.day;
            });
            // Weekly subtotal in signature column
            if (weekTotal > 0) {
                doc.text(weekTotal.toFixed(1), x + cols.signature / 2, y + rowHeight * 0.65, { align: 'center' });
            }
            grandTotal += weekTotal;

            doc.setFont('helvetica', 'normal');
            doc.rect(margin, y, tableWidth, rowHeight);
            y += rowHeight;

            // Vertical column lines
            const blockBottom = y;
            x = margin + cols.name;
            doc.line(x, blockTop, x, blockBottom);
            x += cols.indicator;
            doc.line(x, blockTop, x, blockBottom);
            WEEKDAYS.forEach(() => {
                x += cols.day;
                doc.line(x, blockTop, x, blockBottom);
            });
        });

        // === GRAND TOTAL ROW ===
        doc.setFillColor(235, 235, 235);
        doc.rect(margin, y, tableWidth - 40, grandTotalHeight, 'F');
        doc.rect(margin + tableWidth - 40, y, 40, grandTotalHeight, 'F');
        doc.setFont('helvetica', 'bold');
        doc.setFontSize(10);
        doc.text('Grand Total of Hours', margin + 3, y + grandTotalHeight * 0.65);
        // Print the grand total value
        if (grandTotal > 0) {
            doc.text(grandTotal.toFixed(1), margin + tableWidth - 20, y + grandTotalHeight * 0.65, { align: 'center' });
        }
        doc.setLineWidth(0.4);
        doc.rect(margin, y, tableWidth, grandTotalHeight);
        doc.line(margin + tableWidth - 40, y, margin + tableWidth - 40, y + grandTotalHeight);

    });

    // Planned scheduler rows are not attendance records. Mark every page so a page
    // remains unambiguous after printing or being separated from a batch export.
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
            'PROJECTED SCHEDULE - RECONCILE WITH ACTUAL ATTENDANCE BEFORE SIGNING',
            pageWidth / 2,
            7,
            { align: 'center' },
        );
        doc.setFont('helvetica', 'normal');
        doc.setFontSize(7);
        doc.text('Not an attendance record or proof of service.', pageWidth / 2, pageHeight - 5, { align: 'center' });
        doc.setTextColor(0, 0, 0);
    }

    return doc;
}

export function generateTimesheetsPDF(
    children: ChildAttendanceData[],
    monthYear: string
): void {
    const doc = buildTimesheetDoc(children, monthYear);
    const filename = `DRAFT_PROJECTED_timesheets_${monthYear.replace(/\s+/g, '_').replace(/[^a-zA-Z0-9_-]/g, '')}.pdf`;
    doc.save(filename);
}

export function generateTimesheetsPDFBlob(
    children: ChildAttendanceData[],
    monthYear: string
): Blob {
    const doc = buildTimesheetDoc(children, monthYear);
    return doc.output('blob');
}

export function generateSingleChildTimesheetPDF(
    child: ChildAttendanceData,
    monthYear: string
): void {
    generateTimesheetsPDF([child], monthYear);
}

export function generateSingleChildTimesheetBlob(
    child: ChildAttendanceData,
    monthYear: string
): Blob {
    return generateTimesheetsPDFBlob([child], monthYear);
}
