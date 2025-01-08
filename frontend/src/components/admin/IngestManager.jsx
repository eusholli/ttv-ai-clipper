import { useState, useEffect } from 'react';
import { useAuth } from '@clerk/clerk-react';
import './IngestManager.css';

// Workflow states that match backend states
const WorkflowState = {
  PENDING: "pending",
  FETCHING_HTML: "fetching_html",
  HTML_FETCHED: "html_fetched",
  EDITING_METADATA: "editing_metadata",
  FETCHING_VIDEO: "fetching_video",
  VIDEO_FETCHED: "video_fetched",
  GENERATING_CLIPS: "generating_clips",
  COMPLETED: "completed",
  FAILED: "failed"
};

const IngestManager = () => {
  const { getToken } = useAuth();
  const [url, setUrl] = useState('');
  const [email, setEmail] = useState('');
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [expandedJobs, setExpandedJobs] = useState(new Set());
  const [jobDetailsMap, setJobDetailsMap] = useState(new Map());
  const [editingMetadataId, setEditingMetadataId] = useState(null);
  const [editingTranscriptId, setEditingTranscriptId] = useState(null);
  const [showLog, setShowLog] = useState(false);
  const [logContent, setLogContent] = useState('');

  // Fetch jobs and set up polling if needed
  useEffect(() => {
    let interval;
    
    const pollIfNeeded = async () => {
      const currentJobs = await fetchJobs();
      const activeJobs = currentJobs.filter(job => 
        job.status !== 'completed' && job.status !== 'failed' && job.status !== 'deleted'
      );
      
      // If there are active jobs, start polling
      if (activeJobs.length > 0) {
        // Clear any existing interval before setting a new one
        if (interval) {
          clearInterval(interval);
        }
        
        interval = setInterval(async () => {
          const updatedJobs = await fetchJobs();
          const stillActive = updatedJobs.filter(job => 
            job.status !== 'completed' && job.status !== 'failed' && job.status !== 'deleted'
          );
          
          // If no more active jobs, clear the interval
          if (stillActive.length === 0) {
            clearInterval(interval);
            interval = null;
          } else {
            // Update details for expanded jobs using current expandedJobs state
            expandedJobs.forEach(jobId => {
              fetchJobDetails(jobId);
            });
          }
        }, 1000);
      }
    };

    // Initial fetch and poll setup
    pollIfNeeded();

    // Cleanup function to clear interval when component unmounts or dependencies change
    return () => {
      if (interval) {
        clearInterval(interval);
      }
    };
  }, [expandedJobs]); // Re-run when expandedJobs changes

  // Fetch job details for expanded jobs
  useEffect(() => {
    expandedJobs.forEach(jobId => {
      if (!jobDetailsMap.has(jobId)) {
        fetchJobDetails(jobId);
      }
    });
  }, [expandedJobs]);

  const fetchJobs = async () => {
    try {
      const token = await getToken();
      const response = await fetch('/api/admin/jobs', {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      if (!response.ok) throw new Error('Failed to fetch jobs');
      const data = await response.json();
      setJobs(data);
      return data;
    } catch (err) {
      console.error('Error fetching jobs:', err);
      setError('Failed to fetch jobs');
      return [];
    }
  };

  const fetchJobDetails = async (jobId) => {
    try {
      const token = await getToken();
      const response = await fetch(`/api/admin/jobs/${jobId}/details`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      if (!response.ok) throw new Error('Failed to fetch job details');
      const data = await response.json();
      setJobDetailsMap(prev => new Map(prev).set(jobId, data));
    } catch (err) {
      console.error('Error fetching job details:', err);
      setError('Failed to fetch job details');
    }
  };

  const fetchJobLog = async (jobId) => {
    try {
      const token = await getToken();
      const response = await fetch(`/api/admin/jobs/${jobId}/log`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      if (!response.ok) throw new Error('Failed to fetch job log');
      const data = await response.json();
      setLogContent(data.log);
      setShowLog(true);
    } catch (err) {
      console.error('Error fetching job log:', err);
      setError('Failed to fetch job log');
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      const token = await getToken();
      const response = await fetch('/api/admin/jobs', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ url, user_email: email })
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || 'Failed to create job');
      }

      // Use the returned job record directly
      const newJob = await response.json();
      setJobs(prevJobs => [newJob, ...prevJobs]); // Add new job to start of list
      setExpandedJobs(prev => new Set(prev).add(newJob.id));
      fetchJobDetails(newJob.id);

      // Clear form
      setUrl('');
      setEmail('');
    } catch (err) {
      console.error('Error creating job:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleUpdateMetadata = async (jobId, metadata) => {
    try {
      const token = await getToken();
      const response = await fetch(`/api/admin/jobs/${jobId}/metadata`, {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(metadata)
      });

      if (!response.ok) throw new Error('Failed to update metadata');
      
      setEditingMetadataId(null);
      await fetchJobDetails(jobId);
    } catch (err) {
      console.error('Error updating metadata:', err);
      setError(err.message);
    }
  };

  const handleUpdateTranscript = async (jobId, segments) => {
    try {
      const token = await getToken();
      const response = await fetch(`/api/admin/jobs/${jobId}/transcript`, {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(segments)
      });

      if (!response.ok) throw new Error('Failed to update transcript');
      
      setEditingTranscriptId(null);
      await fetchJobDetails(jobId);
    } catch (err) {
      console.error('Error updating transcript:', err);
      setError(err.message);
    }
  };

  const [archiveDeleteStatus, setArchiveDeleteStatus] = useState('idle'); // 'idle', 'deleting', 'polling'
  const [archiveDeleteProgress, setArchiveDeleteProgress] = useState(0);

  const handleDeleteArchive = async () => {
    if (!window.confirm('Are you sure you want to delete all archived jobs? This cannot be undone.')) {
      return;
    }

    setArchiveDeleteStatus('deleting');
    setError(null);

    try {
      // Get initial count of archived jobs
      const initialJobs = await fetchJobs();
      const initialArchivedCount = initialJobs.filter(job => 
        job.status === 'completed' || job.status === 'failed' || job.status === 'deleted'
      ).length;

      if (initialArchivedCount === 0) {
        setArchiveDeleteStatus('idle');
        return;
      }

      // Start deletion
      const token = await getToken();
      const response = await fetch('/api/admin/jobs/archive', {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });

      if (!response.ok) throw new Error('Failed to delete archive');
      
      const data = await response.json();
      console.log(`Deleting ${data.deleted_jobs} archived jobs`);

      // Start polling to check progress
      setArchiveDeleteStatus('polling');
      let remainingJobs = initialArchivedCount;
      
      const pollInterval = setInterval(async () => {
        const currentJobs = await fetchJobs();
        const currentArchivedCount = currentJobs.filter(job => 
          job.status === 'completed' || job.status === 'failed' || job.status === 'deleted'
        ).length;

        // Calculate and update progress
        const deletedCount = initialArchivedCount - currentArchivedCount;
        const progress = Math.round((deletedCount / initialArchivedCount) * 100);
        setArchiveDeleteProgress(progress);

        if (currentArchivedCount === 0) {
          clearInterval(pollInterval);
          setArchiveDeleteStatus('idle');
          setArchiveDeleteProgress(0);
        }

        remainingJobs = currentArchivedCount;
      }, 1000);

      // Safety cleanup after 30 seconds
      setTimeout(() => {
        if (pollInterval) {
          clearInterval(pollInterval);
          setArchiveDeleteStatus('idle');
          setArchiveDeleteProgress(0);
        }
      }, 30000);

    } catch (err) {
      console.error('Error deleting archive:', err);
      setError(err.message);
      setArchiveDeleteStatus('idle');
      setArchiveDeleteProgress(0);
    }
  };

  const handleDeleteContent = async (jobId) => {
    if (!window.confirm('Are you sure you want to delete all content for this job? This cannot be undone.')) {
      return;
    }

    try {
      const token = await getToken();
      const response = await fetch(`/api/admin/jobs/${jobId}/content`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });

      if (!response.ok) throw new Error('Failed to delete content');
      
      await fetchJobDetails(jobId);
      await fetchJobs();
    } catch (err) {
      console.error('Error deleting content:', err);
      setError(err.message);
    }
  };

  const renderMetadataEditor = (jobId) => {
    const jobDetails = jobDetailsMap.get(jobId);
    if (!jobDetails?.metadata) return null;
    const metadata = jobDetails.metadata;

    return (
      <div className="metadata-editor">
        <h3>Edit Metadata</h3>
        <form onSubmit={(e) => {
          e.preventDefault();
          const formData = new FormData(e.target);
          handleUpdateMetadata(jobId, {
            title: formData.get('title'),
            date: formData.get('date'),
            youtube_id: formData.get('youtube_id'),
            source: formData.get('source')
          });
        }}>
          <div className="form-group">
            <label>Title:</label>
            <input name="title" defaultValue={metadata.title || ''} />
          </div>
          <div className="form-group">
            <label>Date:</label>
            <input name="date" defaultValue={metadata.date || ''} />
          </div>
          <div className="form-group">
            <label>YouTube ID:</label>
            <input name="youtube_id" defaultValue={metadata.youtube_id || ''} />
          </div>
          <div className="form-group">
            <label>Source:</label>
            <input name="source" defaultValue={metadata.source || ''} />
          </div>
          <div className="button-group">
            <button type="submit">Save</button>
            <button type="button" onClick={() => setEditingMetadataId(null)}>Cancel</button>
          </div>
        </form>
      </div>
    );
  };

  const renderTranscriptEditor = (jobId) => {
    const jobDetails = jobDetailsMap.get(jobId);
    if (!jobDetails?.transcript) return null;

    return (
      <div className="transcript-editor">
        <h3>Edit Transcript</h3>
        <div className="transcript-segments">
          {jobDetails.transcript.map((segment, index) => (
            <div key={segment.segment_hash} className="transcript-segment">
              <div className="segment-header">
                <span>Segment {index + 1}</span>
                <span>{segment.start_time}s - {segment.end_time}s</span>
              </div>
              <textarea
                defaultValue={segment.text}
                onChange={(e) => {
                  const updatedTranscript = [...jobDetails.transcript];
                  updatedTranscript[index] = {
                    ...segment,
                    text: e.target.value
                  };
                  setJobDetailsMap(prev => new Map(prev).set(jobId, {
                    ...jobDetails,
                    transcript: updatedTranscript
                  }));
                }}
              />
              <div className="segment-metadata">
                <input
                  placeholder="Speaker"
                  defaultValue={segment.speaker || ''}
                  onChange={(e) => {
                    const updatedTranscript = [...jobDetails.transcript];
                    updatedTranscript[index] = {
                      ...segment,
                      speaker: e.target.value
                    };
                    setJobDetailsMap(prev => new Map(prev).set(jobId, {
                      ...jobDetails,
                      transcript: updatedTranscript
                    }));
                  }}
                />
                <input
                  placeholder="Company"
                  defaultValue={segment.company || ''}
                  onChange={(e) => {
                    const updatedTranscript = [...jobDetails.transcript];
                    updatedTranscript[index] = {
                      ...segment,
                      company: e.target.value
                    };
                    setJobDetailsMap(prev => new Map(prev).set(jobId, {
                      ...jobDetails,
                      transcript: updatedTranscript
                    }));
                  }}
                />
              </div>
            </div>
          ))}
        </div>
        <div className="button-group">
          <button onClick={() => handleUpdateTranscript(jobId, jobDetails.transcript)}>Save</button>
          <button onClick={() => setEditingTranscriptId(null)}>Cancel</button>
        </div>
      </div>
    );
  };

  // For jobs list table - only has access to high-level status
  const getStatusColor = (status) => {
    switch (status) {
      case 'completed': return 'status-completed';
      case 'failed': return 'status-failed';
      case 'running': return 'status-running';
      case 'deleted': return 'status-deleted';
      default: return 'status-pending';
    }
  };

  // For job details - has access to detailed workflow state
  const getWorkflowStepClass = (jobDetails, step) => {
    const job = jobDetails.job;
    
    if (job.status === 'completed') return 'completed';
    
    switch (step) {
      case 1: // Fetch HTML
        if (job.detailed_workflow_state === WorkflowState.FETCHING_HTML || 
            job.detailed_workflow_state === WorkflowState.HTML_FETCHED) return 'active';
        if (job.detailed_workflow_state === WorkflowState.FAILED && !job.html_fetch_success) return 'failed';
        if (job.detailed_workflow_state === WorkflowState.HTML_FETCHED || 
            job.detailed_workflow_state === WorkflowState.EDITING_METADATA ||
            job.detailed_workflow_state === WorkflowState.FETCHING_VIDEO ||
            job.detailed_workflow_state === WorkflowState.VIDEO_FETCHED ||
            job.detailed_workflow_state === WorkflowState.GENERATING_CLIPS ||
            job.detailed_workflow_state === WorkflowState.COMPLETED) return 'completed';
        return '';
        
      case 2: // Edit Metadata
        if (job.detailed_workflow_state === WorkflowState.EDITING_METADATA) return 'active';
        if (job.detailed_workflow_state === WorkflowState.FAILED && !job.metadata_edited_at) return 'failed';
        if (job.detailed_workflow_state === WorkflowState.FETCHING_VIDEO ||
            job.detailed_workflow_state === WorkflowState.VIDEO_FETCHED ||
            job.detailed_workflow_state === WorkflowState.GENERATING_CLIPS ||
            job.detailed_workflow_state === WorkflowState.COMPLETED) return 'completed';
        return '';
        
      case 3: // Fetch Video
        if (job.detailed_workflow_state === WorkflowState.FETCHING_VIDEO ||
            job.detailed_workflow_state === WorkflowState.VIDEO_FETCHED) return 'active';
        if (job.detailed_workflow_state === WorkflowState.FAILED && !job.video_fetch_success) return 'failed';
        if (job.detailed_workflow_state === WorkflowState.GENERATING_CLIPS ||
            job.detailed_workflow_state === WorkflowState.COMPLETED) return 'completed';
        return '';
        
      case 4: // Generate Clips
        if (job.detailed_workflow_state === WorkflowState.GENERATING_CLIPS) return 'active';
        if (job.detailed_workflow_state === WorkflowState.FAILED) return 'failed';
        if (job.detailed_workflow_state === WorkflowState.COMPLETED) return 'completed';
        return '';
        
      default:
        return '';
    }
  };

  // Format workflow state for display
  const formatWorkflowState = (state) => {
    if (!state) return '';
    return state.split('_').map(word => 
      word.charAt(0).toUpperCase() + word.slice(1).toLowerCase()
    ).join(' ');
  };

  const formatDate = (dateString) => {
    return new Date(dateString).toLocaleString();
  };

  const renderJobTable = (jobs, title) => (
    <div className="jobs-list">
      <h2>{title}</h2>
      <table>
        <thead>
          <tr>
            <th>ID</th>
            <th>URL</th>
            <th>Status</th>
            <th>Created</th>
            <th>Email</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {jobs.map(job => (
            <>
              <tr key={job.id}>
                <td>{job.id}</td>
                <td className="url-cell">{job.url}</td>
                <td>
                  <span className={`status-badge ${getStatusColor(job.status)}`}>
                    {job.status}
                  </span>
                </td>
                <td>{formatDate(job.created_at)}</td>
                <td>{job.user_email}</td>
                <td>
                  <button 
                    onClick={() => {
                      setExpandedJobs(prev => {
                        const newSet = new Set(prev);
                        if (newSet.has(job.id)) {
                          newSet.delete(job.id);
                        } else {
                          newSet.add(job.id);
                        }
                        return newSet;
                      });
                    }}
                  >
                    {expandedJobs.has(job.id) ? 'Hide Details' : 'Show Details'}
                  </button>
                  <button onClick={() => fetchJobLog(job.id)}>View Log</button>
                </td>
              </tr>
              {expandedJobs.has(job.id) && jobDetailsMap.has(job.id) && (
                <tr>
                  <td colSpan="6">
                    <div className="job-details">
                      <div className="job-status">
                        Current State: {formatWorkflowState(jobDetailsMap.get(job.id).job.detailed_workflow_state)}
                      </div>
                      
                      <div className="workflow-progress">
                        <div className={`workflow-steps ${job.status === 'completed' ? 'all-completed' : ''}`}>
                          <div className={`workflow-step ${getWorkflowStepClass(jobDetailsMap.get(job.id), 1)}`}>1</div>
                          <div className={`workflow-step ${getWorkflowStepClass(jobDetailsMap.get(job.id), 2)}`}>2</div>
                          <div className={`workflow-step ${getWorkflowStepClass(jobDetailsMap.get(job.id), 3)}`}>3</div>
                          <div className={`workflow-step ${getWorkflowStepClass(jobDetailsMap.get(job.id), 4)}`}>4</div>
                        </div>
                        <div className="workflow-labels">
                          <div className="workflow-label">Fetch HTML</div>
                          <div className="workflow-label">Edit Metadata</div>
                          <div className="workflow-label">Fetch Video</div>
                          <div className="workflow-label">Generate Clips</div>
                        </div>
                      </div>

                      <div className="details-actions">
                        <button 
                          onClick={() => setEditingMetadataId(job.id)}
                          disabled={jobDetailsMap.get(job.id).job.detailed_workflow_state === WorkflowState.FETCHING_HTML || 
                                   jobDetailsMap.get(job.id).job.detailed_workflow_state === WorkflowState.FAILED && !jobDetailsMap.get(job.id).job.html_fetch_success}
                        >
                          Edit Metadata
                        </button>
                        <button 
                          onClick={() => setEditingTranscriptId(job.id)}
                          disabled={jobDetailsMap.get(job.id).job.detailed_workflow_state === WorkflowState.FETCHING_HTML || 
                                   jobDetailsMap.get(job.id).job.detailed_workflow_state === WorkflowState.FAILED && !jobDetailsMap.get(job.id).job.html_fetch_success}
                        >
                          Edit Transcript
                        </button>
                        {jobDetailsMap.get(job.id).job.status !== 'deleted' && (
                          <button 
                            onClick={() => handleDeleteContent(job.id)} 
                            className="delete-button"
                            disabled={jobDetailsMap.get(job.id).job.detailed_workflow_state === WorkflowState.FETCHING_HTML ||
                                     jobDetailsMap.get(job.id).job.detailed_workflow_state === WorkflowState.FETCHING_VIDEO ||
                                     jobDetailsMap.get(job.id).job.detailed_workflow_state === WorkflowState.GENERATING_CLIPS}
                          >
                            Delete Content
                          </button>
                        )}
                      </div>

                      {editingMetadataId === job.id && renderMetadataEditor(job.id)}
                      {editingTranscriptId === job.id && renderTranscriptEditor(job.id)}
                    </div>
                  </td>
                </tr>
              )}
            </>
          ))}
        </tbody>
      </table>
    </div>
  );

  return (
    <div className="ingest-manager">
      <h1>Content Ingest Manager</h1>
      
      <form onSubmit={handleSubmit} className="ingest-form">
        <div className="form-group">
          <label htmlFor="url">URL to Ingest:</label>
          <input
            type="url"
            id="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            required
            placeholder="https://example.com/transcript"
          />
        </div>

        <div className="form-group">
          <label htmlFor="email">Notification Email:</label>
          <input
            type="email"
            id="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            placeholder="user@example.com"
          />
        </div>

        <button type="submit" disabled={loading}>
          {loading ? 'Creating Job...' : 'Start Ingest'}
        </button>

        {error && <div className="error-message">{error}</div>}
      </form>

      {/* Active Jobs Table */}
      {renderJobTable(
        jobs.filter(job => job.status !== 'completed' && job.status !== 'failed' && job.status !== 'deleted'),
        'Active Jobs'
      )}

      {/* Archive Table */}
      <div>
        <div className="archive-header">
          <h2>Archive</h2>
          <button 
            onClick={handleDeleteArchive}
            className="delete-button"
            disabled={archiveDeleteStatus !== 'idle'}
          >
            {archiveDeleteStatus === 'deleting' ? 'Initiating Deletion...' :
             archiveDeleteStatus === 'polling' ? `Deleting Archive (${archiveDeleteProgress}%)` :
             'Delete All Archived Jobs'}
          </button>
        </div>
        {renderJobTable(
          jobs.filter(job => job.status === 'completed' || job.status === 'failed' || job.status === 'deleted'),
          ''
        )}
      </div>

      {showLog && (
        <div className="log-viewer">
          <h2>Job Log</h2>
          <button onClick={() => setShowLog(false)} className="close-button">Close</button>
          <pre className="log-content">{logContent}</pre>
        </div>
      )}
    </div>
  );
};

export default IngestManager;
