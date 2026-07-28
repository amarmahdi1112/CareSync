// ============================================
// Child Detail View - Redesigned
// Matches FamilyDetail pattern with dropdown & tabs
// ============================================

import React, { useState, useRef, useEffect, useMemo } from 'react';
import ObservationReport from './ObservationReport';
import type { ObsChild, ObsMessage } from './ObservationReport';
import ReactMarkdown from 'react-markdown';
import { useParams, useNavigate, Link } from 'react-router-dom';
import {
  PencilIcon,
  TrashIcon,
  HeartIcon,
  ExclamationTriangleIcon,
  CalendarDaysIcon,
  UserGroupIcon,
  PlayIcon,
  PauseIcon,
  ClipboardDocumentListIcon,
  EllipsisHorizontalIcon,
  CheckCircleIcon,
  XCircleIcon,
} from '@heroicons/react/24/outline';
import { UserIcon } from '@heroicons/react/24/solid';

// UI Components
import { ConfirmModal } from '../../../components/ui';

// Use same layout components as families module for consistency
import {
  PageContainer,
  PageHeader,
  ContentCard,
  DetailSkeleton,
  EmptyState,
} from '../../families/components/layout';
import { StatusBadge, AgeGroupBadge } from '../../families/components/cards';

// GraphQL
import { api } from '../../../api/client';
import { useApiQuery } from '../../../api/hooks';

// Types
import type { ChildGraphQL } from '../types';
import { mapAgeGroup, calculateAge } from '../types';

// -------------------- Tab Types --------------------

type TabType = 'overview' | 'medical' | 'attendance';

const tabs: { id: TabType; name: string; icon: React.ElementType }[] = [
  { id: 'overview', name: 'Overview', icon: UserIcon },
  { id: 'medical', name: 'Medical', icon: HeartIcon },
  { id: 'attendance', name: 'Attendance', icon: CalendarDaysIcon },
];

// -------------------- Actions Menu (Same as FamilyDetail) --------------------

const ActionsMenu: React.FC<{
  isActive: boolean;
  onEdit: () => void;
  onDeactivate: () => void;
  onActivate: () => void;
  onDelete: () => void;
}> = ({ isActive, onEdit, onDeactivate, onActivate, onDelete }) => {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <div className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
      >
        <EllipsisHorizontalIcon className="w-5 h-5" />
      </button>
      
      {isOpen && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setIsOpen(false)} />
          <div className="absolute right-0 mt-2 w-48 bg-white rounded-xl shadow-lg border border-gray-200 py-2 z-20">
            <button
              onClick={() => { setIsOpen(false); onEdit(); }}
              className="w-full px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-50 flex items-center gap-2"
            >
              <PencilIcon className="w-4 h-4" />
              Edit Child
            </button>
            <div className="border-t border-gray-100 my-1" />
            {isActive ? (
              <button
                onClick={() => { setIsOpen(false); onDeactivate(); }}
                className="w-full px-4 py-2 text-left text-sm text-amber-600 hover:bg-amber-50 flex items-center gap-2"
              >
                <PauseIcon className="w-4 h-4" />
                Deactivate
              </button>
            ) : (
              <button
                onClick={() => { setIsOpen(false); onActivate(); }}
                className="w-full px-4 py-2 text-left text-sm text-green-600 hover:bg-green-50 flex items-center gap-2"
              >
                <PlayIcon className="w-4 h-4" />
                Activate
              </button>
            )}
            <button
              onClick={() => { setIsOpen(false); onDelete(); }}
              className="w-full px-4 py-2 text-left text-sm text-red-600 hover:bg-red-50 flex items-center gap-2"
            >
              <TrashIcon className="w-4 h-4" />
              Remove Child
            </button>
          </div>
        </>
      )}
    </div>
  );
};

// -------------------- Quick Stat --------------------

const QuickStat: React.FC<{ label: string; value: string | number | React.ReactNode }> = ({ label, value }) => (
  <div className="flex items-center justify-between py-2">
    <span className="text-sm text-gray-500">{label}</span>
    <span className="text-sm font-semibold text-gray-900">{value}</span>
  </div>
);

// -------------------- Info Row --------------------

const InfoRow: React.FC<{ label: string; value?: string | React.ReactNode }> = ({ label, value }) => (
  <div className="flex justify-between items-center py-3 border-b border-gray-50 last:border-0">
    <span className="text-sm text-gray-500">{label}</span>
    <span className="text-sm font-medium text-gray-900">{value || '—'}</span>
  </div>
);

// -------------------- Main Component --------------------

const ChildDetail: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  
  const [activeTab, setActiveTab] = useState<TabType>('overview');
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [showDeactivateModal, setShowDeactivateModal] = useState(false);

  // ── Chat state ──
  const [chatInput, setChatInput] = useState('');
  const [chatMessages, setChatMessages] = useState<Array<{
    id: string; role: string; content: string; imageBase64?: string | null; imageMimeType?: string | null; imagesJson?: string | null; createdAt: string;
  }>>([]);
  const [chatLoading, setChatLoading] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);
  const [pendingImages, setPendingImages] = useState<Array<{ base64: string; mimeType: string; preview: string }>>([]);
  const [showUniversalPrompt, setShowUniversalPrompt] = useState(false);
  const [showObservation, setShowObservation] = useState(false);
  const [universalVersion, setUniversalVersion] = useState<number | null>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const chatFileRef = useRef<HTMLInputElement>(null);

  type PromptResponse = { promptText: string; version: number; imageCount: number; updatedAt: string };
  type ConversationMessage = { id: string; role: string; content: string; imageBase64: string | null; imageMimeType: string | null; imagesJson: string | null; createdAt: string };
  const { data: universalPrompt, refetch: refetchUniversal } = useApiQuery<PromptResponse>('/ai/universal-prompt');
  const universalPromptData = universalPrompt ? { universalPrompt } : undefined;
  const { data: conversationRows = [], loading: conversationLoading, refetch: refetchConversation } = useApiQuery<ConversationMessage[]>(`/ai/children/${id || ''}/conversation`, undefined, Boolean(id));
  const conversationData = useMemo(
    () => ({ childConversation: conversationRows }),
    [conversationRows],
  );

  useEffect(() => {
    setChatMessages([]);
    setChatInput('');
    setPendingImages([]);
    setChatError(null);
  }, [id]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [conversationData, chatMessages]);

  const handleChatImageSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    if (!files.length) return;
    files.forEach(file => {
      const reader = new FileReader();
      reader.onload = () => {
        const dataUrl = reader.result as string;
        setPendingImages(prev => [...prev, { base64: dataUrl.split(',')[1], mimeType: file.type, preview: dataUrl }]);
      };
      reader.readAsDataURL(file);
    });
    e.target.value = '';
  };

  const handleSendMessage = async (presetText?: string) => {
    const text = presetText || chatInput;
    if ((!text.trim() && !pendingImages.length) || !id) return;
    setChatLoading(true);
    setChatError(null);

    const imagesToSend = pendingImages;
    const userEntry = {
      id: `tmp-${Date.now()}`,
      role: 'user',
      content: text || `📷 ${imagesToSend.length > 1 ? imagesToSend.length + ' images' : 'Image'} uploaded for analysis`,
      imageBase64: imagesToSend[0]?.base64 ?? null,
      imageMimeType: imagesToSend[0]?.mimeType ?? null,
      imagesJson: imagesToSend.length > 1 ? JSON.stringify(imagesToSend.map(img => ({ base64: img.base64, mimeType: img.mimeType, preview: img.preview }))) : null,
      createdAt: new Date().toISOString(),
    };
    setChatMessages(prev => [...prev, userEntry]);
    setChatInput('');
    setPendingImages([]);

    try {
      const result = await api.post<{
        message: { id: string; role: string; content: string; createdAt: string };
        universalPromptVersion: number | null;
      }>(`/ai/children/${id}/messages`, {
        message: text || (imagesToSend.length > 0 ? 'Analyze these images and provide behavioral insights.' : ''),
        images: imagesToSend.length > 0 ? imagesToSend.map(img => ({ base64: img.base64, mimeType: img.mimeType })) : undefined,
      });
      if (result) {
        if (result.universalPromptVersion) {
          setUniversalVersion(result.universalPromptVersion);
          refetchUniversal();
        }
        await refetchConversation();
        setChatMessages([]);
      }
    } catch (err: unknown) {
      setChatError(err instanceof Error ? err.message : 'Failed to send message');
      setChatMessages(prev => prev.filter(m => m.id !== userEntry.id));
    } finally {
      setChatLoading(false);
    }
  };

  const handleClearChat = async () => {
    if (!id) return;
    await api.delete(`/ai/children/${id}/conversation`);
    await refetchConversation();
    setChatMessages([]);
    setUniversalVersion(null);
  };

  const { data: childData, loading, error, refetch } = useApiQuery<ChildGraphQL>(`/children/${id || ''}`, undefined, Boolean(id));
  const data = childData ? { child: childData } : undefined;

  const child = data?.child;

  // Handlers
  const handleBack = () => navigate('/children');
  const handleEdit = () => navigate(`/children/${id}/edit`);
  const handleDelete = async () => {
    await api.resources.remove('children', id!);
    setShowDeleteModal(false);
    navigate('/children');
  };
  const handleDeactivate = async () => {
    await api.resources.update('children', id!, { is_active: false });
    setShowDeactivateModal(false);
    await refetch();
  };
  const handleActivate = async () => {
    await api.resources.update('children', id!, { is_active: true });
    await refetch();
  };

  // Loading state
  if (loading) {
    return (
      <PageContainer>
        <DetailSkeleton />
      </PageContainer>
    );
  }

  // Error state
  if (error || !child) {
    return (
      <PageContainer>
        <ContentCard>
          <EmptyState
            icon={<UserIcon className="w-8 h-8 text-red-400" />}
            title="Child not found"
            description="The child you're looking for doesn't exist or has been removed."
            action={{ label: 'Go Back', onClick: handleBack }}
          />
        </ContentCard>
      </PageContainer>
    );
  }

  // Mapped values
  const ageGroup = mapAgeGroup(child.age_group);
  const isActive = child.is_active;
  const age = calculateAge(child.date_of_birth);
  const initials = `${child.first_name[0]}${child.last_name[0]}`;

  return (
    <PageContainer>
      {/* Header - Matching FamilyDetail style */}
      <PageHeader
        title={child.first_name + ' ' + child.last_name}
        description={`Enrolled since ${new Date(child.start_date).toLocaleDateString()}`}
        icon={<UserIcon className="w-6 h-6 text-white" />}
        backLink="/children"
        actions={
          <div className="flex items-center gap-2">
            <StatusBadge status={isActive ? 'active' : 'inactive'} />
            <ActionsMenu
              isActive={isActive}
              onEdit={handleEdit}
              onDeactivate={() => setShowDeactivateModal(true)}
              onActivate={handleActivate}
              onDelete={() => setShowDeleteModal(true)}
            />
          </div>
        }
      />

      {/* Tabs - Same as FamilyDetail */}
      <div className="mb-6">
        <nav className="flex space-x-6 overflow-x-auto">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            const isActiveTab = activeTab === tab.id;
            
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`whitespace-nowrap py-2 px-1 border-b-2 font-medium text-sm transition-colors flex items-center gap-2 ${
                  isActiveTab 
                    ? 'border-primary-500 text-primary-600' 
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
              >
                <Icon className="w-4 h-4" />
                {tab.name}
              </button>
            );
          })}
        </nav>
      </div>

      {/* Content Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Main Content */}
        <div className="lg:col-span-2 space-y-6">
          
          {/* Overview Tab */}
          {activeTab === 'overview' && (
            <>
              {/* Child Profile Card */}
              <ContentCard>
                <div className="flex items-start gap-6">
                  {/* Avatar with initials */}
                  <div className={`w-20 h-20 rounded-2xl flex items-center justify-center text-2xl font-bold ${
                    isActive 
                      ? 'bg-gradient-to-br from-primary-100 to-primary-200 text-primary-600' 
                      : 'bg-gray-100 text-gray-400'
                  }`}>
                    {initials}
                  </div>
                  
                  {/* Basic Info */}
                  <div className="flex-1">
                    <div className="flex items-center gap-3 mb-2">
                      <h2 className="text-xl font-bold text-gray-900">
                        {child.first_name} {child.last_name}
                      </h2>
                      <AgeGroupBadge ageGroup={ageGroup} />
                    </div>
                    <div className="grid grid-cols-2 gap-4 mt-4">
                      <div>
                        <p className="text-xs text-gray-500 uppercase tracking-wider">Age</p>
                        <p className="font-semibold text-gray-900">{age}</p>
                      </div>
                      <div>
                        <p className="text-xs text-gray-500 uppercase tracking-wider">Date of Birth</p>
                        <p className="font-semibold text-gray-900">{new Date(child.date_of_birth).toLocaleDateString()}</p>
                      </div>
                      <div>
                        <p className="text-xs text-gray-500 uppercase tracking-wider">Gender</p>
                        <p className="font-semibold text-gray-900">{child.gender || 'Not specified'}</p>
                      </div>
                      <div>
                        <p className="text-xs text-gray-500 uppercase tracking-wider">Enrollment Date</p>
                        <p className="font-semibold text-gray-900">{new Date(child.start_date).toLocaleDateString()}</p>
                      </div>
                    </div>
                  </div>
                </div>
              </ContentCard>

              {/* Medical Alerts (if any) */}
              {(child.allergies || child.medical_conditions) && (
                <ContentCard
                  title="Health Alerts"
                  actions={
                    <div className="w-9 h-9 rounded-lg bg-red-100 flex items-center justify-center">
                      <ExclamationTriangleIcon className="w-5 h-5 text-red-600" />
                    </div>
                  }
                >
                  <div className="space-y-3">
                    {child.allergies && child.allergies !== 'None' && (
                      <div className="p-4 rounded-xl bg-red-50 border border-red-200">
                        <div className="flex items-start gap-3">
                          <ExclamationTriangleIcon className="w-5 h-5 text-red-500 mt-0.5 flex-shrink-0" />
                          <div>
                            <p className="text-sm font-semibold text-red-800">Allergies</p>
                            <p className="text-sm text-red-700 mt-1">{child.allergies}</p>
                          </div>
                        </div>
                      </div>
                    )}
                    {child.medical_conditions && child.medical_conditions !== 'None' && (
                      <div className="p-4 rounded-xl bg-amber-50 border border-amber-200">
                        <p className="text-sm font-semibold text-amber-800">Medical Conditions</p>
                        <p className="text-sm text-amber-700 mt-1">{child.medical_conditions}</p>
                      </div>
                    )}
                  </div>
                </ContentCard>
              )}

              {/* AI Behavior Insights — Chat */}
              <div className="bg-gradient-to-br from-violet-50 to-purple-50 rounded-xl border border-violet-200 overflow-hidden">

                {/* Header */}
                <div className="flex items-center justify-between px-5 py-3 border-b border-violet-100">
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-violet-500 to-purple-600 flex items-center justify-center shadow-sm shrink-0">
                      <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                      </svg>
                    </div>
                    <div>
                      <h3 className="font-semibold text-gray-900 text-sm">AI Behavior Insights</h3>
                      <p className="text-xs text-violet-500">Persistent chat · learns from images</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {universalVersion && (
                      <span className="text-xs bg-violet-500 text-white px-2 py-0.5 rounded-full font-medium">Universal v{universalVersion}</span>
                    )}
                    <button
                      onClick={() => setShowObservation(true)}
                      disabled={(conversationData?.childConversation ?? []).length === 0}
                      title="Finalize observation report"
                      className="flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-medium bg-violet-600 text-white hover:bg-violet-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                    >
                      <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
                      Finalize
                    </button>
                    <button onClick={handleClearChat} title="Clear conversation" className="p-1.5 rounded-lg text-gray-400 hover:text-red-500 hover:bg-red-50 transition-colors">
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                    </button>
                  </div>
                </div>

                {/* Quick prompts */}
                <div className="px-4 pt-3 flex flex-wrap gap-1.5">
                  {['Development summary', 'Age-appropriate activities', 'Parent report', 'Medical checklist'].map((p) => (
                    <button key={p} onClick={() => handleSendMessage(p)} disabled={chatLoading}
                      className="px-2.5 py-1 text-xs font-medium rounded-full bg-white border border-violet-200 text-violet-700 hover:bg-violet-50 disabled:opacity-40 transition-all">
                      {p}
                    </button>
                  ))}
                </div>

                {/* Messages */}
                <div className="px-4 py-3 space-y-3 max-h-96 overflow-y-auto">
                  {conversationLoading && (
                    <div className="flex items-center gap-2 text-xs text-gray-400 py-6 justify-center">
                      <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>
                      Loading conversation...
                    </div>
                  )}
                  {(conversationData?.childConversation ?? []).length === 0 && chatMessages.length === 0 && !conversationLoading && (
                    <div className="text-center py-8">
                      <div className="w-10 h-10 rounded-full bg-violet-100 flex items-center justify-center mx-auto mb-2">
                        <svg className="w-5 h-5 text-violet-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-3 3v-3z" /></svg>
                      </div>
                      <p className="text-sm text-gray-400">Start a conversation — ask anything or upload an image</p>
                    </div>
                  )}
                  {[...(conversationData?.childConversation ?? []), ...chatMessages].map((msg) => (
                    <div key={msg.id} className={`flex gap-2 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                      {msg.role === 'assistant' && (
                        <div className="w-6 h-6 rounded-full bg-violet-500 flex items-center justify-center shrink-0 mt-1">
                          <svg className="w-3 h-3 text-white" fill="currentColor" viewBox="0 0 20 20"><path fillRule="evenodd" d="M10 9a3 3 0 100-6 3 3 0 000 6zm-7 9a7 7 0 1114 0H3z" clipRule="evenodd" /></svg>
                        </div>
                      )}
                      <div className={`max-w-[80%] rounded-2xl px-3 py-2 text-sm ${msg.role === 'user' ? 'bg-violet-600 text-white rounded-tr-sm' : 'bg-white border border-violet-100 text-gray-700 rounded-tl-sm shadow-sm'}`}>
                        {(() => {
                          const imgs: Array<{ base64: string; mimeType: string; preview?: string }> = msg.imagesJson
                            ? JSON.parse(msg.imagesJson)
                            : (msg.imageBase64 && msg.imageMimeType ? [{ base64: msg.imageBase64, mimeType: msg.imageMimeType }] : []);
                          return imgs.length > 0 ? (
                            <div className={`flex flex-wrap gap-1.5 mb-2 ${imgs.length === 1 ? '' : 'max-w-xs'}`}>
                              {imgs.map((img, i) => (
                                <img
                                  key={i}
                                  src={img.preview || `data:${img.mimeType};base64,${img.base64}`}
                                  alt={`observation-${i}`}
                                  className={`object-cover rounded-lg ${imgs.length === 1 ? 'w-48 h-36' : 'w-24 h-20'}`}
                                />
                              ))}
                            </div>
                          ) : null;
                        })()}
                        <div className={`prose prose-sm max-w-none leading-relaxed ${msg.role === 'user' ? 'prose-invert' : 'prose-gray'}`}>
                          <ReactMarkdown>{msg.content}</ReactMarkdown>
                        </div>
                        <p className={`text-xs mt-1 ${msg.role === 'user' ? 'text-violet-200' : 'text-gray-400'}`}>
                          {new Date(msg.createdAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                        </p>
                      </div>
                    </div>
                  ))}
                  {chatLoading && (
                    <div className="flex gap-2 justify-start">
                      <div className="w-6 h-6 rounded-full bg-violet-500 flex items-center justify-center shrink-0 mt-1">
                        <svg className="w-3 h-3 text-white" fill="currentColor" viewBox="0 0 20 20"><path fillRule="evenodd" d="M10 9a3 3 0 100-6 3 3 0 000 6zm-7 9a7 7 0 1114 0H3z" clipRule="evenodd" /></svg>
                      </div>
                      <div className="bg-white border border-violet-100 rounded-2xl rounded-tl-sm px-4 py-3 shadow-sm">
                        <div className="flex gap-1">
                          <span className="w-2 h-2 bg-violet-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                          <span className="w-2 h-2 bg-violet-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                          <span className="w-2 h-2 bg-violet-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                        </div>
                      </div>
                    </div>
                  )}
                  <div ref={chatEndRef} />
                </div>

                {chatError && (
                  <div className="mx-4 mb-2 p-2 rounded-lg bg-red-50 border border-red-200 text-xs text-red-700">{chatError}</div>
                )}

                {/* Pending images preview */}
                {pendingImages.length > 0 && (
                  <div className="mx-4 mb-2 p-2 bg-white rounded-lg border border-violet-200">
                    <div className="flex flex-wrap gap-2">
                      {pendingImages.map((img, i) => (
                        <div key={i} className="relative group">
                          <img src={img.preview} alt={`pending-${i}`} className="w-14 h-14 rounded-lg object-cover border border-violet-200" />
                          <button
                            onClick={() => setPendingImages(prev => prev.filter((_, idx) => idx !== i))}
                            className="absolute -top-1.5 -right-1.5 w-4 h-4 rounded-full bg-red-500 text-white opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center"
                          >
                            <svg className="w-2.5 h-2.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M6 18L18 6M6 6l12 12" /></svg>
                          </button>
                        </div>
                      ))}
                      <button
                        onClick={() => chatFileRef.current?.click()}
                        className="w-14 h-14 rounded-lg border-2 border-dashed border-violet-300 flex items-center justify-center text-violet-400 hover:border-violet-500 hover:text-violet-500 transition-colors"
                      >
                        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" /></svg>
                      </button>
                    </div>
                    <p className="text-xs text-gray-400 mt-1.5">{pendingImages.length} image{pendingImages.length !== 1 ? 's' : ''} ready — add a message or send</p>
                  </div>
                )}

                {/* Universal prompt viewer */}
                <div className="mx-4 mb-2">
                  <button onClick={() => setShowUniversalPrompt(!showUniversalPrompt)} className="w-full flex items-center justify-between py-2 px-3 rounded-lg bg-white border border-violet-100 text-xs text-gray-500 hover:bg-violet-50 transition-colors">
                    <div className="flex items-center gap-1.5">
                      <svg className="w-3.5 h-3.5 text-violet-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 3H5a2 2 0 00-2 2v4m6-6h10a2 2 0 012 2v4M9 3v18m0 0h10a2 2 0 002-2V9M9 21H5a2 2 0 01-2-2V9m0 0h18" /></svg>
                      <span className="font-medium text-violet-600">Universal Prompt</span>
                      {universalPromptData?.universalPrompt && (
                        <span className="bg-violet-100 text-violet-600 px-1.5 py-0.5 rounded-full">v{universalPromptData.universalPrompt.version} · {universalPromptData.universalPrompt.imageCount} images</span>
                      )}
                    </div>
                    <svg className={`w-3.5 h-3.5 text-gray-400 transition-transform ${showUniversalPrompt ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" /></svg>
                  </button>
                  {showUniversalPrompt && (
                    <div className="mt-1 p-3 rounded-lg bg-gray-50 border border-gray-200">
                      <p className="text-xs text-gray-400 mb-2">Evolves with every image — accumulates patterns across all children.</p>
                      <pre className="text-xs text-gray-600 whitespace-pre-wrap font-mono leading-relaxed">{universalPromptData?.universalPrompt?.promptText || 'Loading...'}</pre>
                      {universalPromptData?.universalPrompt && (
                        <p className="text-xs text-gray-400 mt-2">Last updated: {new Date(universalPromptData.universalPrompt.updatedAt).toLocaleString()}</p>
                      )}
                    </div>
                  )}
                </div>

                {/* Input bar */}
                <div className="px-4 pb-4">
                  <div className="flex gap-2 items-center bg-white rounded-xl border border-violet-200 p-1.5">
                    <input ref={chatFileRef} type="file" accept="image/*" multiple className="hidden" onChange={handleChatImageSelect} />
                    <button onClick={() => chatFileRef.current?.click()} className="p-1.5 rounded-lg text-violet-400 hover:bg-violet-50 transition-colors shrink-0" title="Attach image">
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" /></svg>
                    </button>
                    <input
                      type="text"
                      value={chatInput}
                      onChange={(e) => setChatInput(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && handleSendMessage()}
                      placeholder="Ask about this child..."
                      disabled={chatLoading}
                      className="flex-1 text-sm bg-transparent focus:outline-none px-1 disabled:opacity-50"
                    />
                    <button
                      onClick={() => handleSendMessage()}
                      disabled={chatLoading || (!chatInput.trim() && !pendingImages.length)}
                      className="p-1.5 rounded-lg bg-violet-600 text-white hover:bg-violet-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors shrink-0"
                    >
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" /></svg>
                    </button>
                  </div>
                </div>

              </div>

              {/* Future Features Grid */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* Development Milestones */}
                <div className="group relative bg-gradient-to-br from-emerald-50 to-teal-50 rounded-xl border border-emerald-200/50 p-5 hover:shadow-md transition-all">
                  <div className="absolute top-3 right-3">
                    <span className="px-2 py-1 bg-emerald-100 text-emerald-600 text-xs font-medium rounded-full">
                      Coming Soon
                    </span>
                  </div>
                  <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-emerald-500 to-teal-500 flex items-center justify-center mb-3">
                    <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4M7.835 4.697a3.42 3.42 0 001.946-.806 3.42 3.42 0 014.438 0 3.42 3.42 0 001.946.806 3.42 3.42 0 013.138 3.138 3.42 3.42 0 00.806 1.946 3.42 3.42 0 010 4.438 3.42 3.42 0 00-.806 1.946 3.42 3.42 0 01-3.138 3.138 3.42 3.42 0 00-1.946.806 3.42 3.42 0 01-4.438 0 3.42 3.42 0 00-1.946-.806 3.42 3.42 0 01-3.138-3.138 3.42 3.42 0 00-.806-1.946 3.42 3.42 0 010-4.438 3.42 3.42 0 00.806-1.946 3.42 3.42 0 013.138-3.138z" />
                    </svg>
                  </div>
                  <h3 className="font-semibold text-gray-900 mb-1">Development Milestones</h3>
                  <p className="text-sm text-gray-500">
                    Track cognitive, social, and physical milestones by age group.
                  </p>
                </div>

                {/* Progress Reports */}
                <div className="group relative bg-gradient-to-br from-blue-50 to-cyan-50 rounded-xl border border-blue-200/50 p-5 hover:shadow-md transition-all">
                  <div className="absolute top-3 right-3">
                    <span className="px-2 py-1 bg-blue-100 text-blue-600 text-xs font-medium rounded-full">
                      Coming Soon
                    </span>
                  </div>
                  <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500 to-cyan-500 flex items-center justify-center mb-3">
                    <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                  </div>
                  <h3 className="font-semibold text-gray-900 mb-1">Progress Reports</h3>
                  <p className="text-sm text-gray-500">
                    Generate shareable reports for parents with photos and insights.
                  </p>
                </div>

                {/* Daily Logs */}
                <div className="group relative bg-gradient-to-br from-amber-50 to-orange-50 rounded-xl border border-amber-200/50 p-5 hover:shadow-md transition-all">
                  <div className="absolute top-3 right-3">
                    <span className="px-2 py-1 bg-amber-100 text-amber-600 text-xs font-medium rounded-full">
                      Coming Soon
                    </span>
                  </div>
                  <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-amber-500 to-orange-500 flex items-center justify-center mb-3">
                    <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                  </div>
                  <h3 className="font-semibold text-gray-900 mb-1">Daily Activity Logs</h3>
                  <p className="text-sm text-gray-500">
                    Meals, naps, activities, and mood tracking throughout the day.
                  </p>
                </div>
              </div>

              {/* Staff Notes & Observations */}
              <ContentCard
                title="Staff Notes & Observations"
                actions={
                  <span className="px-2 py-1 bg-gray-100 text-gray-500 text-xs font-medium rounded-full">
                    Coming Soon
                  </span>
                }
              >
                <div className="text-center py-8">
                  <div className="w-16 h-16 mx-auto mb-4 rounded-2xl bg-gradient-to-br from-gray-100 to-gray-200 flex items-center justify-center">
                    <svg className="w-8 h-8 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                    </svg>
                  </div>
                  <h3 className="text-lg font-semibold text-gray-900 mb-2">Staff Observations</h3>
                  <p className="text-sm text-gray-500 max-w-md mx-auto mb-4">
                    Teachers and staff will be able to log daily observations, behavioral notes, and learning moments that feed into the AI analysis system.
                  </p>
                  <div className="flex flex-wrap justify-center gap-2">
                    <span className="px-3 py-1 bg-violet-50 text-violet-600 text-xs font-medium rounded-full">AI-Powered</span>
                    <span className="px-3 py-1 bg-blue-50 text-blue-600 text-xs font-medium rounded-full">Questionnaires</span>
                    <span className="px-3 py-1 bg-emerald-50 text-emerald-600 text-xs font-medium rounded-full">Photo Logs</span>
                    <span className="px-3 py-1 bg-amber-50 text-amber-600 text-xs font-medium rounded-full">Mood Tracking</span>
                  </div>
                </div>
              </ContentCard>

              {/* Learning & Goals */}
              <ContentCard
                title="Learning Goals & Curriculum"
                actions={
                  <span className="px-2 py-1 bg-gray-100 text-gray-500 text-xs font-medium rounded-full">
                    Coming Soon
                  </span>
                }
              >
                <div className="space-y-4">
                  {/* Goal Categories Preview */}
                  <div className="grid grid-cols-3 gap-3">
                    <div className="text-center p-4 rounded-xl bg-pink-50 border border-pink-100">
                      <div className="text-2xl mb-1">🎨</div>
                      <p className="text-xs font-medium text-gray-700">Creative</p>
                      <p className="text-xs text-gray-400">Arts & Expression</p>
                    </div>
                    <div className="text-center p-4 rounded-xl bg-blue-50 border border-blue-100">
                      <div className="text-2xl mb-1">🔢</div>
                      <p className="text-xs font-medium text-gray-700">Cognitive</p>
                      <p className="text-xs text-gray-400">Math & Logic</p>
                    </div>
                    <div className="text-center p-4 rounded-xl bg-green-50 border border-green-100">
                      <div className="text-2xl mb-1">🤝</div>
                      <p className="text-xs font-medium text-gray-700">Social</p>
                      <p className="text-xs text-gray-400">Communication</p>
                    </div>
                  </div>
                  <p className="text-sm text-gray-500 text-center">
                    Set personalized learning goals aligned with age-appropriate curriculum standards.
                  </p>
                </div>
              </ContentCard>
            </>
          )}

          {/* Medical Tab */}
          {activeTab === 'medical' && (
            <ContentCard
              title="Medical Information"
              actions={
                <div className="w-9 h-9 rounded-lg bg-red-100 flex items-center justify-center">
                  <HeartIcon className="w-5 h-5 text-red-600" />
                </div>
              }
            >
              <div className="space-y-1">
                <InfoRow label="Health Care Number" value={child.health_care_number} />
                <InfoRow label="Family Doctor" value={child.doctor_name} />
                <InfoRow label="Doctor Phone" value={child.doctor_phone} />
                <InfoRow 
                  label="Immunizations Up to Date" 
                  value={
                    child.immunization_up_to_date ? (
                      <span className="flex items-center gap-1.5 text-green-600 font-medium">
                        <CheckCircleIcon className="w-4 h-4" /> Yes
                      </span>
                    ) : child.immunization_up_to_date === false ? (
                      <span className="flex items-center gap-1.5 text-red-600 font-medium">
                        <XCircleIcon className="w-4 h-4" /> No
                      </span>
                    ) : (
                      <span className="text-gray-400">Not specified</span>
                    )
                  } 
                />
              </div>

              {/* Medical Details */}
              <div className="mt-6 space-y-4">
                {child.allergies && (
                  <div className="p-4 rounded-xl bg-red-50 border border-red-200">
                    <p className="text-sm font-semibold text-red-800 mb-1">Allergies</p>
                    <p className="text-sm text-red-700">{child.allergies}</p>
                  </div>
                )}
                {child.medical_conditions && (
                  <div className="p-4 rounded-xl bg-amber-50 border border-amber-200">
                    <p className="text-sm font-semibold text-amber-800 mb-1">Medical Conditions</p>
                    <p className="text-sm text-amber-700">{child.medical_conditions}</p>
                  </div>
                )}
                {child.medications && (
                  <div className="p-4 rounded-xl bg-blue-50 border border-blue-200">
                    <p className="text-sm font-semibold text-blue-800 mb-1">Current Medications</p>
                    <p className="text-sm text-blue-700">{child.medications}</p>
                  </div>
                )}
                {!child.allergies && !child.medical_conditions && !child.medications && (
                  <EmptyState
                    icon={<HeartIcon className="w-8 h-8 text-green-400" />}
                    title="No medical notes"
                    description="No allergies, conditions, or medications recorded."
                  />
                )}
              </div>
            </ContentCard>
          )}

          {/* Attendance Tab */}
          {activeTab === 'attendance' && (
            <ContentCard
              title="Attendance History"
              actions={
                <div className="w-9 h-9 rounded-lg bg-purple-100 flex items-center justify-center">
                  <CalendarDaysIcon className="w-5 h-5 text-purple-600" />
                </div>
              }
            >
              <div className="text-center py-12">
                <ClipboardDocumentListIcon className="w-16 h-16 mx-auto mb-4 text-gray-300" />
                <h3 className="text-lg font-semibold text-gray-900 mb-2">Coming Soon</h3>
                <p className="text-sm text-gray-500 max-w-sm mx-auto">
                  Attendance tracking and history will be available here once enabled.
                </p>
              </div>
            </ContentCard>
          )}
        </div>

        {/* Sidebar */}
        <div className="space-y-6">
          {/* Quick Info */}
          <ContentCard title="Quick Info">
            <div className="divide-y divide-gray-100">
              <QuickStat label="Age Group" value={<AgeGroupBadge ageGroup={ageGroup} />} />
              <QuickStat label="Age" value={age} />
              <QuickStat label="Status" value={<StatusBadge status={isActive ? 'active' : 'inactive'} />} />
              <QuickStat label="Enrolled" value={new Date(child.start_date).toLocaleDateString()} />
            </div>
          </ContentCard>

          {/* Family Link */}
          <ContentCard title="Family">
            <Link
              to={`/families/${child.family_id}`}
              className="flex items-center gap-3 p-4 bg-gray-50 rounded-xl hover:bg-gray-100 hover:shadow-sm transition-all"
            >
              <div className="w-10 h-10 bg-gradient-to-br from-primary-100 to-primary-200 rounded-xl flex items-center justify-center">
                <UserGroupIcon className="w-5 h-5 text-primary-600" />
              </div>
              <div>
                <p className="font-medium text-gray-900">View Family</p>
                <p className="text-sm text-gray-500">Guardians & contacts</p>
              </div>
            </Link>
          </ContentCard>

          {/* Quick Actions */}
          <ContentCard title="Actions">
            <div className="space-y-2">
              <button onClick={handleEdit} className="w-full btn btn-secondary justify-start">
                <PencilIcon className="w-4 h-4" />
                Edit Child
              </button>
              <Link to={`/families/${child.family_id}`} className="w-full btn btn-secondary justify-start">
                <UserGroupIcon className="w-4 h-4" />
                View Family
              </Link>
            </div>
          </ContentCard>
        </div>
      </div>

      {/* Delete Confirmation Modal */}
      <ConfirmModal
        isOpen={showDeleteModal}
        onConfirm={handleDelete}
        onCancel={() => setShowDeleteModal(false)}
        title="Remove Child"
        message={`Are you sure you want to remove ${child.first_name} ${child.last_name}? This action cannot be undone.`}
        confirmLabel="Remove"
        variant="danger"
      />

      {/* Deactivate Confirmation Modal */}
      <ConfirmModal
        isOpen={showDeactivateModal}
        onConfirm={handleDeactivate}
        onCancel={() => setShowDeactivateModal(false)}
        title="Deactivate Child"
        message={`Are you sure you want to deactivate ${child.first_name} ${child.last_name}? If this is the only active child in the family, the entire family will also be deactivated. You can reactivate later.`}
        confirmLabel="Deactivate"
        variant="warning"
      />

      {/* Observation Report Modal */}
      {showObservation && (
        <ObservationReport
          child={child as ObsChild}
          messages={(conversationData?.childConversation ?? []) as ObsMessage[]}
          onClose={() => setShowObservation(false)}
        />
      )}
    </PageContainer>
  );
};

export default ChildDetail;
