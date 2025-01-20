import React from 'react';
import { useAuth, useUser } from '@clerk/clerk-react';
import { DownloadButton, EmailButton } from '../buttons';

const ResultItem = ({ 
  result, 
  selectedClips, 
  setSelectedClips,
  downloading,
  setDownloading,
  emailing,
  setEmailing,
  getSubjectDisplayString
}) => {
  const { isSignedIn } = useAuth();
  const { user } = useUser();
  
  const formatSecondsToTime = (seconds) => {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const remainingSeconds = seconds % 60;
    
    if (hours > 0) {
      return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(remainingSeconds).padStart(2, '0')}`;
    }
    return `${String(minutes).padStart(2, '0')}:${String(remainingSeconds).padStart(2, '0')}`;
  };

  const startParam = result.start_time === 0 ? "0" : result.start_time - 1;
  const endParam = result.end_time === 0 ? "" : `&end=${result.end_time + 1}`;
  const ytUrl = `https://youtube.com/embed/${result.youtube_id}?start=${startParam}${endParam}&autoplay=0&rel=0`;

  return (
    <article className="result-item">
      <div className="result-content">
        <div className="result-header">
          <input
            type="checkbox"
            className={`clip-checkbox ${!isSignedIn || !user?.unsafeMetadata?.stripeCustomerId ? 'inactive' : ''}`}
            checked={selectedClips.includes(result.segment_hash)}
            onChange={(e) => {
              if (e.target.checked) {
                setSelectedClips([...selectedClips, result.segment_hash]);
              } else {
                setSelectedClips(selectedClips.filter(hash => hash !== result.segment_hash));
              }
            }}
            disabled={!isSignedIn || !user?.unsafeMetadata?.stripeCustomerId}
          />
          <h2 className="result-title">{result.title}</h2>
        </div>
        <div className="result-meta">
          {result.speaker} · {result.company}
        </div>
        <div className="result-time">
          {formatSecondsToTime(result.start_time)} - {formatSecondsToTime(result.end_time)} · {result.date.split('T')[0]}
          <span className="result-score">Match Score: {(result.score * 100).toFixed(1)}%</span>
        </div>
        <p className="result-text">{result.text}</p>
        {result.subjects && (
          <div className="result-tags">
            Tags: {result.subjects.map(subject => getSubjectDisplayString(subject)).join(', ')}
          </div>
        )}
      </div>
      <div className="result-video">
        <iframe
          src={ytUrl}
          width="300"
          height="169"
          frameBorder="0"
          allowFullScreen
        />
        {result.download && (
          <>
            <DownloadButton 
              result={result}
              downloading={downloading}
              setDownloading={setDownloading}
            />
            <EmailButton
              result={result}
              emailing={emailing}
              setEmailing={setEmailing}
            />
          </>
        )}
      </div>
    </article>
  );
};

export default ResultItem;
