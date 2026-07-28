import React from 'react';
import './PrintableTimesheet.css';

// Types
export interface ChildTimesheetData {
    name: string;
    dateOfBirth: string;
}

export interface WeeklyAttendance {
    weekStartDate: string; // e.g., "2026-01-13"
    days: {
        date: string;
        dayName: 'MON' | 'TUES' | 'WEDS' | 'THURS' | 'FRI';
        startTime1?: string;
        endTime1?: string;
        startTime2?: string;
        endTime2?: string;
    }[];
}

interface TimesheetRowProps {
    child?: ChildTimesheetData;
    attendance?: WeeklyAttendance;
    rowNumber: number;
    isBlank?: boolean;
}

const formatTime = (time?: string): string => {
    if (!time) return '';
    const [h, m] = time.split(':').map(Number);
    const period = h >= 12 ? 'PM' : 'AM';
    const hour = h > 12 ? h - 12 : h === 0 ? 12 : h;
    return `${hour}:${m.toString().padStart(2, '0')} ${period}`;
};

const TimesheetRow: React.FC<TimesheetRowProps> = ({ child, attendance, rowNumber, isBlank }) => {
    const days = ['MON', 'TUES', 'WEDS', 'THURS', 'FRI'] as const;

    // Get attendance data for each day
    const getAttendanceForDay = (dayName: string) => {
        if (!attendance) return null;
        return attendance.days.find(d => d.dayName === dayName);
    };

    return (
        <div className="timesheet-child-block">
            {/* Name row */}
            <div className="timesheet-row name-row">
                <div className="cell name-cell">
                    <span className="row-number">{rowNumber}</span>
                    <div className="name-input">
                        {!isBlank && child?.name}
                    </div>
                </div>
                {days.map(day => {
                    const dayData = getAttendanceForDay(day);
                    return (
                        <div key={day} className="cell day-cell time-value">
                            {dayData?.startTime1 && formatTime(dayData.startTime1)}
                        </div>
                    );
                })}
                <div className="cell signature-cell"></div>
            </div>

            {/* D.O.B. row with OUT for session 1 */}
            <div className="timesheet-row">
                <div className="cell name-cell">
                    <span className="label">D.O.B:</span>
                    <div className="dob-input">
                        {!isBlank && child?.dateOfBirth}
                    </div>
                </div>
                {days.map(day => {
                    const dayData = getAttendanceForDay(day);
                    return (
                        <div key={day} className="cell day-cell">
                            <span className="out-label">OUT</span>
                            <span className="time-value">{dayData?.endTime1 && formatTime(dayData.endTime1)}</span>
                        </div>
                    );
                })}
                <div className="cell signature-cell"></div>
            </div>

            {/* IN row for session 2 */}
            <div className="timesheet-row">
                <div className="cell name-cell"></div>
                {days.map(day => {
                    const dayData = getAttendanceForDay(day);
                    return (
                        <div key={day} className="cell day-cell">
                            <span className="in-label">IN</span>
                            <span className="time-value">{dayData?.startTime2 && formatTime(dayData.startTime2)}</span>
                        </div>
                    );
                })}
                <div className="cell signature-cell"></div>
            </div>

            {/* OUT row for session 2 */}
            <div className="timesheet-row">
                <div className="cell name-cell"></div>
                {days.map(day => {
                    const dayData = getAttendanceForDay(day);
                    return (
                        <div key={day} className="cell day-cell">
                            <span className="out-label">OUT</span>
                            <span className="time-value">{dayData?.endTime2 && formatTime(dayData.endTime2)}</span>
                        </div>
                    );
                })}
                <div className="cell signature-cell"></div>
            </div>

            {/* INITIAL row */}
            <div className="timesheet-row">
                <div className="cell name-cell"><span className="label">INITIAL</span></div>
                {days.map(day => (
                    <div key={day} className="cell day-cell"></div>
                ))}
                <div className="cell signature-cell"></div>
            </div>

            {/* TOTAL row */}
            <div className="timesheet-row total-row">
                <div className="cell name-cell"><span className="label">TOTAL</span></div>
                {days.map(day => (
                    <div key={day} className="cell day-cell"></div>
                ))}
                <div className="cell signature-cell"></div>
            </div>
        </div>
    );
};

// Props for PDF/print mode with data
export interface PrintableTimesheetProps {
    children?: {
        child: ChildTimesheetData;
        attendance: WeeklyAttendance;
    }[];
    monthYear?: string;
    showPrintButton?: boolean;
}

const PrintableTimesheet: React.FC<PrintableTimesheetProps> = ({
    children: childrenData,
    monthYear,
    showPrintButton = true
}) => {
    const currentDate = new Date();
    const displayMonthYear = monthYear || currentDate.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });

    // If no children data provided, show blank form for manual entry
    const isBlankForm = !childrenData || childrenData.length === 0;
    const rowsToShow = isBlankForm ? 6 : childrenData.length;

    return (
        <div className="printable-timesheet">
            <div className="timesheet-paper">
                {/* Header */}
                <div className="timesheet-header">
                    <div className="header-left">
                        <span className="header-title">Direct Childcare Hours: Parents Please Initial and Sign</span>
                    </div>
                    <div className="header-right">
                        <span className="month-display">{displayMonthYear}</span>
                    </div>
                </div>

                {/* Column Headers */}
                <div className="timesheet-columns">
                    <div className="cell header-cell name-header">Name</div>
                    <div className="cell header-cell day-header">MON</div>
                    <div className="cell header-cell day-header">TUES</div>
                    <div className="cell header-cell day-header">WEDS</div>
                    <div className="cell header-cell day-header">THURS</div>
                    <div className="cell header-cell day-header">FRI</div>
                    <div className="cell header-cell signature-header">Signature</div>
                </div>

                {/* Child Rows */}
                {isBlankForm ? (
                    // Blank form for manual entry
                    Array.from({ length: rowsToShow }, (_, idx) => (
                        <TimesheetRow key={idx} rowNumber={idx + 1} isBlank />
                    ))
                ) : (
                    // Populated form with data
                    childrenData.map((data, idx) => (
                        <TimesheetRow
                            key={idx}
                            rowNumber={idx + 1}
                            child={data.child}
                            attendance={data.attendance}
                        />
                    ))
                )}

                {/* Grand Total */}
                <div className="grand-total-row">
                    <div className="cell grand-total-label">Grand Total of Hours</div>
                    <div className="cell grand-total-value"></div>
                </div>

                {/* Print Button - hidden when printing */}
                {showPrintButton && (
                    <div className="print-controls no-print">
                        <button className="print-btn" onClick={() => window.print()}>
                            🖨️ Print Timesheet
                        </button>
                    </div>
                )}
            </div>
        </div>
    );
};

export default PrintableTimesheet;
