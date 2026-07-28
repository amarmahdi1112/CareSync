// ============================================
// Agent Mode - AI Invoice Generator
// ============================================

import React, { useState, useRef, useEffect, useCallback } from 'react';
import { useInvoiceAgent, type ParsedInvoice, type AgentMessage, type AgentAction } from '../hooks/useInvoiceAgent';
import ReactMarkdown from 'react-markdown';

// ---- Invoice Card Component ----
const InvoiceCard: React.FC<{
  invoice: ParsedInvoice;
  index: number;
  messageIndex: number;
  isCreated: boolean;
  onCreateInvoice: (invoice: ParsedInvoice, msgIdx: number, invIdx: number) => Promise<void>;
}> = ({ invoice, index, messageIndex, isCreated, onCreateInvoice }) => {
  const [creating, setCreating] = useState(false);
  const [result, setResult] = useState<string | null>(null);

  const handleCreate = async () => {
    setCreating(true);
    try {
      await onCreateInvoice(invoice, messageIndex, index);
      setResult('success');
    } catch {
      setResult('error');
    }
    setCreating(false);
  };

  const totalAmount = invoice.total_estimate ||
    invoice.line_items.reduce((sum, item) => sum + (item.amount || 0), 0);

  return (
    <div className={`
      relative overflow-hidden rounded-xl border transition-all duration-300
      ${isCreated
        ? 'border-green-300 bg-green-50/80'
        : 'border-purple-200/60 bg-white/80 hover:border-purple-300 hover:shadow-lg'
      }
    `}
    style={{ backdropFilter: 'blur(10px)' }}
    >
      {/* Card Header */}
      <div className={`
        px-5 py-3 border-b flex items-center justify-between
        ${isCreated ? 'border-green-200 bg-green-100/50' : 'border-purple-100 bg-gradient-to-r from-purple-50 to-indigo-50'}
      `}>
        <div className="flex items-center gap-3">
          <div className={`
            w-8 h-8 rounded-lg flex items-center justify-center text-sm font-bold
            ${isCreated ? 'bg-green-500 text-white' : 'bg-purple-600 text-white'}
          `}>
            {isCreated ? '✓' : `#${index + 1}`}
          </div>
          <div>
            <h4 className="text-sm font-semibold text-gray-900">
              {invoice.client_name || invoice.family_name || 'Invoice'}
            </h4>
            {invoice.client_email && (
              <p className="text-xs text-gray-500">{invoice.client_email}</p>
            )}
          </div>
        </div>
        <div className="text-right">
          <p className="text-lg font-bold text-gray-900">${totalAmount.toFixed(2)}</p>
          {invoice.children && invoice.children.length > 0 && (
            <p className="text-xs text-gray-500">{invoice.children.join(', ')}</p>
          )}
        </div>
      </div>

      {/* Line Items */}
      <div className="px-5 py-3">
        <div className="space-y-2">
          {invoice.line_items.map((item, i) => (
            <div key={i} className="flex items-center justify-between text-sm">
              <div className="flex items-center gap-2 min-w-0 flex-1">
                <span className={`
                  inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wide
                  ${item.item_type === 'daycare_subsidy' ? 'bg-blue-100 text-blue-700' :
                    item.item_type === 'service_hourly' ? 'bg-amber-100 text-amber-700' :
                    item.item_type === 'service_flat' ? 'bg-teal-100 text-teal-700' :
                    'bg-gray-100 text-gray-600'}
                `}>
                  {item.item_type === 'daycare_subsidy' ? 'Care' :
                   item.item_type === 'service_hourly' ? 'Hourly' :
                   item.item_type === 'service_flat' ? 'Flat' : 'Product'}
                </span>
                <span className="text-gray-700 truncate">{item.description}</span>
              </div>
              <div className="text-right ml-3 flex-shrink-0">
                {item.item_type === 'daycare_subsidy' && item.full_rate && item.subsidy_amount ? (
                  <div>
                    <span className="text-gray-400 line-through text-xs mr-1">${item.full_rate.toFixed(2)}</span>
                    <span className="font-medium text-gray-900">${item.amount.toFixed(2)}</span>
                  </div>
                ) : (
                  <span className="font-medium text-gray-900">${item.amount.toFixed(2)}</span>
                )}
              </div>
            </div>
          ))}
        </div>

        {/* Date & Notes */}
        <div className="mt-3 pt-3 border-t border-gray-100 flex items-center justify-between text-xs text-gray-500">
          <div className="flex gap-3">
            {invoice.issue_date && <span>Issued: {invoice.issue_date}</span>}
            {invoice.due_date && <span>Due: {invoice.due_date}</span>}
          </div>
          {invoice.period_start && invoice.period_end && (
            <span>Period: {invoice.period_start} → {invoice.period_end}</span>
          )}
        </div>
      </div>

      {/* Actions */}
      <div className="px-5 py-3 border-t border-gray-100 bg-gray-50/50">
        {isCreated ? (
          <div className="flex items-center gap-2 text-green-700 text-sm font-medium">
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
            Invoice created as draft
          </div>
        ) : result === 'error' ? (
          <div className="flex items-center gap-2 text-red-600 text-sm">
            <span>⚠️ Failed to create. Try again.</span>
            <button onClick={handleCreate} className="ml-auto px-3 py-1 text-xs font-medium bg-red-100 text-red-700 rounded-lg hover:bg-red-200 transition-colors">
              Retry
            </button>
          </div>
        ) : (
          <button
            onClick={handleCreate}
            disabled={creating}
            className="w-full flex items-center justify-center gap-2 px-4 py-2 text-sm font-semibold rounded-lg
              bg-gradient-to-r from-purple-600 to-indigo-600 text-white
              hover:from-purple-700 hover:to-indigo-700
              disabled:opacity-50 disabled:cursor-not-allowed
              transition-all duration-200 shadow-sm hover:shadow-md"
          >
            {creating ? (
              <>
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                Creating...
              </>
            ) : (
              <>
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                </svg>
                Create Invoice
              </>
            )}
          </button>
        )}
      </div>
    </div>
  );
};

// ---- Action Button Component ----
const ActionButton: React.FC<{
  action: AgentAction;
  onExecute: (action: AgentAction) => void;
  disabled: boolean;
}> = ({ action, onExecute, disabled }) => (
  <button
    onClick={() => onExecute(action)}
    disabled={disabled}
    className="group flex items-center gap-3 w-full px-4 py-3 rounded-xl border border-gray-200 bg-white
      hover:border-purple-300 hover:bg-purple-50/50 hover:shadow-md
      disabled:opacity-50 disabled:cursor-not-allowed
      transition-all duration-200 text-left"
  >
    <span className="text-2xl flex-shrink-0">{action.icon}</span>
    <div className="flex-1 min-w-0">
      <p className="text-sm font-semibold text-gray-900 group-hover:text-purple-700 transition-colors">
        {action.label}
      </p>
      <p className="text-xs text-gray-500 truncate">{action.description}</p>
    </div>
    <svg className="w-5 h-5 text-gray-300 group-hover:text-purple-400 transition-colors flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
    </svg>
  </button>
);

// ---- Message Bubble Component ----
const MessageBubble: React.FC<{
  message: AgentMessage;
  messageIndex: number;
  isInvoiceCreated: (msgIdx: number, invIdx: number) => boolean;
  onCreateInvoice: (invoice: ParsedInvoice, msgIdx: number, invIdx: number) => Promise<void>;
  onCreateAll: (invoices: ParsedInvoice[], msgIdx: number) => Promise<void>;
  onExecuteAction: (action: AgentAction) => void;
  onPrintInvoices: (ids: string[]) => void;
  onDownloadInvoices: (ids: string[]) => void;
  onDownloadZip: (ids: string[]) => void;
  isProcessing: boolean;
}> = ({ message, messageIndex, isInvoiceCreated, onCreateInvoice, onCreateAll, onExecuteAction, onPrintInvoices, onDownloadInvoices, onDownloadZip, isProcessing }) => {
  const [creatingAll, setCreatingAll] = useState(false);

  const isUser = message.role === 'user';
  const isSystem = message.role === 'system';
  const hasInvoices = message.invoices && message.invoices.length > 0;
  const hasActions = message.actions && message.actions.length > 0;
  const hasCreatedIds = message.createdInvoiceIds && message.createdInvoiceIds.length > 0;
  const allCreated = hasInvoices && message.invoices!.every((_, i) => isInvoiceCreated(messageIndex, i));

  const handleCreateAll = async () => {
    if (!hasInvoices) return;
    setCreatingAll(true);
    await onCreateAll(message.invoices!, messageIndex);
    setCreatingAll(false);
  };

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} animate-fadeSlideIn`}>
      <div className={`${isUser ? 'max-w-[80%]' : 'w-full max-w-[90%]'}`}>
        {/* Avatar & Name */}
        <div className={`flex items-center gap-2 mb-1.5 ${isUser ? 'justify-end' : 'justify-start'}`}>
          {!isUser && (
            <div className={`w-6 h-6 rounded-full flex items-center justify-center flex-shrink-0 ${
              isSystem
                ? 'bg-gradient-to-br from-amber-400 to-orange-500'
                : 'bg-gradient-to-br from-purple-500 to-indigo-600'
            }`}>
              {isSystem ? (
                <svg className="w-3.5 h-3.5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
              ) : (
                <svg className="w-3.5 h-3.5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 3.104v5.714a2.25 2.25 0 01-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 014.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15.3M14.25 3.104c.251.023.501.05.75.082M19.8 15.3l-1.57.393A9.065 9.065 0 0112 15a9.065 9.065 0 00-6.23.693L5 14.5m14.8.8l1.402 1.402c1.232 1.232.65 3.318-1.067 3.611l-.078.013A97.37 97.37 0 0112 21a97.37 97.37 0 01-8.057-.415l-.078-.013c-1.717-.293-2.3-2.379-1.067-3.611L5 14.5" />
                </svg>
              )}
            </div>
          )}
          <span className="text-xs font-medium text-gray-400">
            {isUser ? 'You' : isSystem ? 'System Analysis' : 'AI Agent'}
          </span>
          {message.confidence !== undefined && message.confidence > 0 && !isUser && !isSystem && (
            <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${
              message.confidence >= 0.8 ? 'bg-green-100 text-green-700' :
              message.confidence >= 0.5 ? 'bg-yellow-100 text-yellow-700' :
              'bg-red-100 text-red-700'
            }`}>
              {Math.round(message.confidence * 100)}% confidence
            </span>
          )}
        </div>

        {/* Message Content */}
        <div className={`
          rounded-2xl px-4 py-3 text-sm leading-relaxed
          ${isUser
            ? 'bg-gradient-to-r from-purple-600 to-indigo-600 text-white rounded-br-md'
            : isSystem
              ? 'bg-gradient-to-br from-slate-50 to-gray-100 border border-gray-200 text-gray-800 rounded-bl-md shadow-sm'
              : 'bg-white border border-gray-200 text-gray-800 rounded-bl-md shadow-sm'
          }
        `}>
          {isUser ? (
            <div className="whitespace-pre-wrap">{message.content}</div>
          ) : (
            <div className="prose prose-sm max-w-none prose-p:my-1 prose-li:my-0.5 prose-strong:text-gray-900">
              <ReactMarkdown>{message.content}</ReactMarkdown>
            </div>
          )}
        </div>

        {/* Action Buttons (for system context message) */}
        {hasActions && (
          <div className="mt-3 space-y-2">
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider px-1">Quick Actions</p>
            <div className="grid gap-2 sm:grid-cols-2">
              {message.actions!.map(action => (
                <ActionButton
                  key={action.id}
                  action={action}
                  onExecute={onExecuteAction}
                  disabled={isProcessing}
                />
              ))}
            </div>
          </div>
        )}

        {/* Invoice Cards */}
        {hasInvoices && (
          <div className="mt-3 space-y-3">
            {message.invoices!.length > 1 && !allCreated && (
              <button
                onClick={handleCreateAll}
                disabled={creatingAll}
                className="w-full flex items-center justify-center gap-2 px-4 py-2.5 text-sm font-semibold rounded-xl
                  bg-gradient-to-r from-emerald-500 to-teal-600 text-white
                  hover:from-emerald-600 hover:to-teal-700
                  disabled:opacity-50 disabled:cursor-not-allowed
                  transition-all duration-200 shadow-md hover:shadow-lg"
              >
                {creatingAll ? (
                  <>
                    <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    Creating all invoices...
                  </>
                ) : (
                  <>🚀 Create All {message.invoices!.length} Invoices</>
                )}
              </button>
            )}

            {allCreated && message.invoices!.length > 1 && (
              <div className="flex items-center justify-center gap-2 px-4 py-2.5 text-sm font-medium text-green-700 bg-green-50 rounded-xl border border-green-200">
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                All {message.invoices!.length} invoices created as drafts
              </div>
            )}

            <div className={`grid gap-3 ${message.invoices!.length > 1 ? 'sm:grid-cols-2' : ''}`}>
              {message.invoices!.map((inv, i) => (
                <InvoiceCard
                  key={i}
                  invoice={inv}
                  index={i}
                  messageIndex={messageIndex}
                  isCreated={isInvoiceCreated(messageIndex, i)}
                  onCreateInvoice={onCreateInvoice}
                />
              ))}
            </div>
          </div>
        )}

        {/* Print & Download buttons for bulk-generated invoices */}
        {hasCreatedIds && (
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              onClick={() => onPrintInvoices(message.createdInvoiceIds!)}
              className="flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg
                border border-gray-300 bg-white text-gray-700
                hover:bg-gray-50 hover:border-gray-400 transition-all shadow-sm"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z" />
              </svg>
              Print All
            </button>
            <button
              onClick={() => onDownloadInvoices(message.createdInvoiceIds!)}
              className="flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg
                border border-gray-300 bg-white text-gray-700
                hover:bg-gray-50 hover:border-gray-400 transition-all shadow-sm"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
              </svg>
              Download CSV
            </button>
            <button
              onClick={() => onDownloadZip(message.createdInvoiceIds!)}
              className="flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg
                bg-gradient-to-r from-violet-600 to-purple-600 text-white
                hover:from-violet-700 hover:to-purple-700 transition-all shadow-sm hover:shadow-md"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4" />
              </svg>
              Download ZIP
            </button>
          </div>
        )}

        {/* Timestamp */}
        <p className={`text-[10px] text-gray-400 mt-1 ${isUser ? 'text-right' : 'text-left'}`}>
          {message.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
        </p>
      </div>
    </div>
  );
};

// ---- Processing Indicator ----
const ProcessingIndicator: React.FC = () => (
  <div className="flex justify-start animate-fadeSlideIn">
    <div className="max-w-[85%]">
      <div className="flex items-center gap-2 mb-1.5">
        <div className="w-6 h-6 rounded-full bg-gradient-to-br from-purple-500 to-indigo-600 flex items-center justify-center">
          <svg className="w-3.5 h-3.5 text-white animate-pulse" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 3.104v5.714a2.25 2.25 0 01-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 014.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15.3M14.25 3.104c.251.023.501.05.75.082M19.8 15.3l-1.57.393A9.065 9.065 0 0112 15a9.065 9.065 0 00-6.23.693L5 14.5m14.8.8l1.402 1.402c1.232 1.232.65 3.318-1.067 3.611l-.078.013A97.37 97.37 0 0112 21a97.37 97.37 0 01-8.057-.415l-.078-.013c-1.717-.293-2.3-2.379-1.067-3.611L5 14.5" />
          </svg>
        </div>
        <span className="text-xs font-medium text-gray-400">AI Agent</span>
      </div>
      <div className="rounded-2xl rounded-bl-md px-5 py-4 bg-white border border-gray-200 shadow-sm">
        <div className="flex items-center gap-3">
          <div className="flex gap-1">
            <div className="w-2 h-2 rounded-full bg-purple-400 animate-bounce" style={{ animationDelay: '0ms' }} />
            <div className="w-2 h-2 rounded-full bg-purple-400 animate-bounce" style={{ animationDelay: '150ms' }} />
            <div className="w-2 h-2 rounded-full bg-purple-400 animate-bounce" style={{ animationDelay: '300ms' }} />
          </div>
          <span className="text-sm text-gray-500">Processing your request...</span>
        </div>
      </div>
    </div>
  </div>
);

// ---- Loading State ----
const LoadingState: React.FC = () => (
  <div className="flex flex-col items-center justify-center h-full gap-4">
    <div className="relative">
      <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-purple-100 to-indigo-100 flex items-center justify-center">
        <svg className="w-8 h-8 text-purple-500 animate-pulse" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.75 3.104v5.714a2.25 2.25 0 01-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 014.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15.3M14.25 3.104c.251.023.501.05.75.082M19.8 15.3l-1.57.393A9.065 9.065 0 0112 15a9.065 9.065 0 00-6.23.693L5 14.5m14.8.8l1.402 1.402c1.232 1.232.65 3.318-1.067 3.611A97.37 97.37 0 0112 21a97.37 97.37 0 01-8.057-.415c-1.717-.293-2.3-2.379-1.067-3.611L5 14.5" />
        </svg>
      </div>
      <div className="absolute -bottom-1 -right-1 w-6 h-6 rounded-full bg-purple-500 flex items-center justify-center">
        <div className="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin" />
      </div>
    </div>
    <div className="text-center">
      <p className="text-sm font-semibold text-gray-700">Loading your invoicing data...</p>
      <p className="text-xs text-gray-400 mt-1">Analyzing families, funding sources, and existing invoices</p>
    </div>
  </div>
);

// ---- Main Agent Mode Component ----
const AgentMode: React.FC = () => {
  const {
    messages,
    isProcessing,
    isLoading,
    sendMessage,
    executeBulkAction,
    createInvoiceFromParsed,
    createAllInvoices,
    clearConversation,
    isInvoiceCreated,
    printCreatedInvoices,
    downloadCreatedInvoices,
    downloadInvoicesAsZip,
  } = useInvoiceAgent();

  const [inputText, setInputText] = useState('');
  const chatEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isProcessing]);

  const handleInputChange = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInputText(e.target.value);
    const ta = e.target;
    ta.style.height = 'auto';
    ta.style.height = Math.min(ta.scrollHeight, 300) + 'px';
  }, []);

  const handleSend = useCallback(async () => {
    if (!inputText.trim() || isProcessing) return;
    const text = inputText;
    setInputText('');
    if (textareaRef.current) textareaRef.current.style.height = 'auto';
    await sendMessage(text);
  }, [inputText, isProcessing, sendMessage]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }, [handleSend]);

  const handleCreateInvoice = useCallback(async (invoice: ParsedInvoice, msgIdx: number, invIdx: number) => {
    await createInvoiceFromParsed(invoice, msgIdx, invIdx);
  }, [createInvoiceFromParsed]);

  const handleCreateAll = useCallback(async (invoices: ParsedInvoice[], msgIdx: number) => {
    await createAllInvoices(invoices, msgIdx);
  }, [createAllInvoices]);

  const handleExecuteAction = useCallback((action: AgentAction) => {
    executeBulkAction(action);
  }, [executeBulkAction]);

  return (
    <div className="flex flex-col h-[calc(100vh-280px)] min-h-[500px]">
      {/* Header */}
      <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-purple-700 via-indigo-700 to-violet-800 p-6 mb-4 shadow-xl">
        <div className="absolute top-0 right-0 w-64 h-64 bg-white/5 rounded-full -translate-y-1/2 translate-x-1/2" />
        <div className="absolute bottom-0 left-0 w-40 h-40 bg-white/5 rounded-full translate-y-1/2 -translate-x-1/2" />
        <div className="absolute top-4 right-8 text-white/10 text-6xl">✨</div>

        <div className="relative flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 rounded-xl bg-white/15 backdrop-blur-sm flex items-center justify-center shadow-inner">
              <svg className="w-7 h-7 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.75 3.104v5.714a2.25 2.25 0 01-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 014.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15.3M14.25 3.104c.251.023.501.05.75.082M19.8 15.3l-1.57.393A9.065 9.065 0 0112 15a9.065 9.065 0 00-6.23.693L5 14.5m14.8.8l1.402 1.402c1.232 1.232.65 3.318-1.067 3.611A97.37 97.37 0 0112 21a97.37 97.37 0 01-8.057-.415c-1.717-.293-2.3-2.379-1.067-3.611L5 14.5" />
              </svg>
            </div>
            <div>
              <h2 className="text-xl font-bold text-white flex items-center gap-2">
                AI Agent Mode
                <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-400/20 text-emerald-200 border border-emerald-400/30">
                  POWERED BY GEMINI
                </span>
              </h2>
              <p className="text-sm text-purple-200 mt-0.5">
                I'll analyze your data, suggest invoices, and generate them for you
              </p>
            </div>
          </div>

          {messages.length > 0 && (
            <button
              onClick={clearConversation}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white/70 hover:text-white bg-white/10 hover:bg-white/20 rounded-lg transition-all backdrop-blur-sm"
            >
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
              Refresh
            </button>
          )}
        </div>
      </div>

      {/* Chat Area */}
      <div className="flex-1 overflow-y-auto rounded-xl border border-gray-200 bg-gray-50/50 p-4 space-y-4 custom-scrollbar">
        {isLoading ? (
          <LoadingState />
        ) : (
          <>
            {messages.map((msg, i) => (
              <MessageBubble
                key={msg.id}
                message={msg}
                messageIndex={i}
                isInvoiceCreated={isInvoiceCreated}
                onCreateInvoice={handleCreateInvoice}
                onCreateAll={handleCreateAll}
                onExecuteAction={handleExecuteAction}
                onPrintInvoices={printCreatedInvoices}
                onDownloadInvoices={downloadCreatedInvoices}
                onDownloadZip={downloadInvoicesAsZip}
                isProcessing={isProcessing}
              />
            ))}
            {isProcessing && <ProcessingIndicator />}
            <div ref={chatEndRef} />
          </>
        )}
      </div>

      {/* Input Area */}
      <div className="mt-3 flex gap-2 items-end">
        <div className="flex-1 relative">
          <textarea
            ref={textareaRef}
            value={inputText}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            placeholder="Paste an email, describe what to invoice, or ask about your data..."
            rows={2}
            className="w-full resize-none rounded-xl border border-gray-300 bg-white px-4 py-3 pr-12 text-sm
              placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-purple-500
              transition-all shadow-sm"
            disabled={isProcessing || isLoading}
          />
          <div className="absolute right-2 bottom-2 text-[10px] text-gray-300">
            ⏎ Enter · ⇧⏎ new line
          </div>
        </div>
        <button
          onClick={handleSend}
          disabled={!inputText.trim() || isProcessing || isLoading}
          className="flex-shrink-0 w-12 h-12 rounded-xl bg-gradient-to-r from-purple-600 to-indigo-600
            text-white flex items-center justify-center
            hover:from-purple-700 hover:to-indigo-700
            disabled:opacity-40 disabled:cursor-not-allowed
            transition-all duration-200 shadow-md hover:shadow-lg"
        >
          {isProcessing ? (
            <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
          ) : (
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5" />
            </svg>
          )}
        </button>
      </div>
    </div>
  );
};

export default AgentMode;
