import React, { useEffect, useState, useRef } from 'react';
import { useNavigation } from 'react-router-dom';

const TopLoader: React.FC = () => {
  const navigation = useNavigation();
  const [progress, setProgress] = useState(0);
  const [visible, setVisible] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (navigation.state === 'loading') {
      // Start loading
      setVisible(true);
      setProgress(0);
      
      // Simulate progress (fast at first, then slows down)
      let currentProgress = 0;
      intervalRef.current = setInterval(() => {
        currentProgress += Math.random() * 15;
        if (currentProgress > 90) {
          currentProgress = 90; // Never reach 100 until actually loaded
          if (intervalRef.current) {
            clearInterval(intervalRef.current);
          }
        }
        setProgress(currentProgress);
      }, 200);
    } else if (navigation.state === 'idle' && visible) {
      // Complete loading
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
      setProgress(100);
      
      // Hide after animation completes
      setTimeout(() => {
        setVisible(false);
        setProgress(0);
      }, 300);
    }

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, [navigation.state, visible]);

  if (!visible && progress === 0) return null;

  return (
    <div className="fixed top-0 left-0 right-0 z-[9999] h-1 bg-transparent pointer-events-none">
      <div
        className="h-full bg-gradient-to-r from-primary-500 via-primary-400 to-primary-600 shadow-lg shadow-primary-500/50 transition-all duration-200 ease-out"
        style={{
          width: `${progress}%`,
          opacity: progress === 100 ? 0 : 1,
          transition: progress === 100 ? 'width 200ms, opacity 300ms' : 'width 200ms',
        }}
      />
      {/* Glow effect at the end */}
      {visible && progress < 100 && (
        <div
          className="absolute top-0 h-full w-24 bg-gradient-to-r from-transparent via-white/30 to-transparent animate-pulse"
          style={{ left: `calc(${progress}% - 3rem)` }}
        />
      )}
    </div>
  );
};

export default TopLoader;
