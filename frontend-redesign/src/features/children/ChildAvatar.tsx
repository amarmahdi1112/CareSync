import { useEffect, useRef, useState } from 'react';
import { CameraIcon } from '@heroicons/react/24/outline';
import styled from 'styled-components';
import { fetchChildPhoto } from './childrenApi';

const Frame = styled.span<{ $size: number; $rounded: boolean }>`
  position: relative;
  display: grid;
  width: ${({ $size }) => $size}px;
  height: ${({ $size }) => $size}px;
  flex: 0 0 auto;
  place-items: center;
  overflow: hidden;
  border: 1px solid ${({ theme }) => theme.color.cyan};
  border-radius: ${({ $rounded, $size }) => $rounded ? '50%' : `${Math.max(11, Math.round($size * .3))}px ${Math.max(5, Math.round($size * .12))}px ${Math.max(11, Math.round($size * .3))}px ${Math.max(5, Math.round($size * .12))}px`};
  color: ${({ theme }) => theme.color.cyan};
  background: linear-gradient(145deg, color-mix(in srgb, ${({ theme }) => theme.color.cyan} 10%, ${({ theme }) => theme.color.surfaceStrong}), color-mix(in srgb, ${({ theme }) => theme.color.plasma} 9%, ${({ theme }) => theme.color.surfaceStrong}));
  font-family: 'CareSync Display', sans-serif;
  font-size: ${({ $size }) => Math.max(10, Math.round($size * .26))}px;
  font-weight: 600;
  letter-spacing: -.02em;
  box-shadow: ${({ theme }) => theme.shadow.cyan};
  img { width: 100%; height: 100%; object-fit: cover; }
  svg { width: 38%; opacity: .52; }
`;

interface ChildAvatarProps {
  firstName: string;
  lastName: string;
  photoUrl?: string | null;
  photoUpdatedAt?: string | null;
  size?: number;
  rounded?: boolean;
  className?: string;
}

export default function ChildAvatar({
  firstName,
  lastName,
  photoUrl,
  photoUpdatedAt,
  size = 44,
  rounded = false,
  className,
}: ChildAvatarProps) {
  const frameRef = useRef<HTMLSpanElement>(null);
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const [nearViewport, setNearViewport] = useState(() => typeof IntersectionObserver === 'undefined');

  useEffect(() => {
    const frame = frameRef.current;
    if (!frame || typeof IntersectionObserver === 'undefined') {
      setNearViewport(true);
      return;
    }
    const observer = new IntersectionObserver(([entry]) => {
      if (!entry.isIntersecting) return;
      setNearViewport(true);
      observer.disconnect();
    }, { rootMargin: '240px' });
    observer.observe(frame);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    setFailed(false);
    setObjectUrl((current) => {
      if (current) URL.revokeObjectURL(current);
      return null;
    });
    if (!photoUrl || !nearViewport) {
      return;
    }
    const controller = new AbortController();
    let createdUrl: string | null = null;
    fetchChildPhoto(photoUrl, controller.signal)
      .then((blob) => {
        if (controller.signal.aborted) return;
        createdUrl = URL.createObjectURL(blob);
        setObjectUrl((current) => {
          if (current) URL.revokeObjectURL(current);
          return createdUrl;
        });
      })
      .catch(() => {
        if (!controller.signal.aborted) setFailed(true);
      });
    return () => {
      controller.abort();
      if (createdUrl) URL.revokeObjectURL(createdUrl);
    };
  }, [nearViewport, photoUrl, photoUpdatedAt]);

  const initials = `${firstName.charAt(0)}${lastName.charAt(0)}`.toUpperCase();
  const label = `${firstName} ${lastName} profile photo`;
  return <Frame ref={frameRef} className={className} $size={size} $rounded={rounded} role="img" aria-label={label}>
    {objectUrl ? <img src={objectUrl} alt="" /> : failed ? <CameraIcon aria-hidden="true" /> : initials}
  </Frame>;
}
