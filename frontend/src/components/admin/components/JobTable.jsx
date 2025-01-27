import React, { useState } from 'react';
import { WorkflowState } from '../constants';
import { getStatusColor, formatWorkflowState, formatDate, getWorkflowStepClass } from '../utils';
import { fetchJobLog, deleteContent, processTranscript } from '../api';
import ContentEditor from './ContentEditor';
import ButtonWithStatus from './ButtonWithStatus';

const JobTable = ({
  jobs, 
  title, 
  expandedJobs, 
  setExpandedJobs, 
  jobDetailsMap,
  onJobDetailsUpdate,
  getToken,
  setError,
  onLogFetched
}) => {
  const [editingContentId, setEditingContentId] = useState(null);
  const [loadingStates, setLoadingStates] = useState({});
  const [viewingLogId, setViewingLogId] = useState(null);

  const handleProcessTranscript = async (jobId) => {
    setLoadingStates(prev => ({ ...prev, [`process-${jobId}`]: 'Initiating process...' }));
    try {
      await processTranscript(jobId, getToken);
      setLoadingStates(prev => ({ ...prev, [`process-${jobId}`]: 'Started processing...' }));
      // Update job details immediately
      await onJobDetailsUpdate(jobId);
      // Force a refresh of the main jobs list to move the job to active table
      const event = new CustomEvent('jobStatusChanged', { detail: { jobId } });
      window.dispatchEvent(event);
      
      // Clear loading state after a brief delay to show "Started" message
      setTimeout(() => {
        setLoadingStates(prev => {
          const newState = { ...prev };
          delete newState[`process-${jobId}`];
          return newState;
        });
      }, 2000);
    } catch (err) {
      setError(err.message);
      setLoadingStates(prev => {
        const newState = { ...prev };
        delete newState[`process-${jobId}`];
        return newState;
      });
    }
  };

  const handleDeleteContent = async (jobId) => {
    if (!window.confirm('Are you sure you want to delete all content for this job? This cannot be undone.')) {
      return;
    }

    setLoadingStates(prev => ({ ...prev, [`delete-${jobId}`]: 'Deleting content...' }));
    try {
      await deleteContent(jobId, getToken);
      
      // Update job details immediately
      await onJobDetailsUpdate(jobId);
      
      // Dispatch event to trigger jobs list refresh
      const event = new CustomEvent('jobStatusChanged', { detail: { jobId } });
      window.dispatchEvent(event);
      
      setLoadingStates(prev => {
        const newState = { ...prev };
        delete newState[`delete-${jobId}`];
        return newState;
      });
    } catch (err) {
      setError(err.message);
      setLoadingStates(prev => {
        const newState = { ...prev };
        delete newState[`delete-${jobId}`];
        return newState;
      });
    }
  };

  const handleLogView = async (jobId) => {
    setViewingLogId(jobId);
    try {
      const data = await fetchJobLog(jobId, getToken);
      onLogFetched(data.log);
    } catch (err) {
      setError(err.message);
    } finally {
      setViewingLogId(null);
    }
  };

  return (
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
            <React.Fragment key={job.id}>
              <tr>
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
                  <ButtonWithStatus 
                    onClick={() => {
                      setLoadingStates(prev => ({ ...prev, [`details-${job.id}`]: true }));
                      setExpandedJobs(prev => {
                        const newSet = new Set(prev);
                        if (newSet.has(job.id)) {
                          newSet.delete(job.id);
                        } else {
                          newSet.add(job.id);
                        }
                        return newSet;
                      });
                      // Clear loading state after a brief delay
                      setTimeout(() => {
                        setLoadingStates(prev => {
                          const newState = { ...prev };
                          delete newState[`details-${job.id}`];
                          return newState;
                        });
                      }, 300);
                    }}
                    isLoading={!!loadingStates[`details-${job.id}`]}
                    loadingText="Loading..."
                  >
                    {expandedJobs.has(job.id) ? 'Hide Details' : 'Show Details'}
                  </ButtonWithStatus>
                  <ButtonWithStatus 
                    onClick={() => handleLogView(job.id)}
                    isLoading={viewingLogId === job.id}
                    loadingText="Loading log..."
                  >
                    View Log
                  </ButtonWithStatus>
                </td>
              </tr>
              {expandedJobs.has(job.id) && jobDetailsMap.has(job.id) && (
                <tr>
                  <td colSpan="6">
                    <div className="job-details">
                      {jobDetailsMap.get(job.id)?.job && (
                        <>
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
                        </>
                      )}

                      {jobDetailsMap.get(job.id)?.job && (
                        <div className="details-actions">
                          <>
                            <ButtonWithStatus 
                              onClick={() => setEditingContentId(job.id)}
                              disabled={jobDetailsMap.get(job.id).job.detailed_workflow_state === WorkflowState.FETCHING_HTML || 
                                       jobDetailsMap.get(job.id).job.detailed_workflow_state === WorkflowState.FAILED && !jobDetailsMap.get(job.id).job.html_fetch_success}
                            >
                              Edit Content
                            </ButtonWithStatus>
                            <ButtonWithStatus
                              onClick={() => handleProcessTranscript(job.id)}
                              disabled={
                                !jobDetailsMap.get(job.id).metadata?.title ||
                                !jobDetailsMap.get(job.id).metadata?.date ||
                                !jobDetailsMap.get(job.id).metadata?.youtube_id ||
                                !jobDetailsMap.get(job.id).job.parsing_status?.success
                              }
                              isLoading={!!loadingStates[`process-${job.id}`]}
                              loadingText={loadingStates[`process-${job.id}`]}
                              title={
                                !jobDetailsMap.get(job.id).job.parsing_status?.success
                                  ? `Parsing failed: ${jobDetailsMap.get(job.id).job.parsing_status?.error || 'Unknown error'}`
                                  : "Process the transcript to generate clips"
                              }
                            >
                              Process Transcript
                            </ButtonWithStatus>
                          </>
                          {jobDetailsMap.get(job.id).job.status !== 'deleted' && (
                            <ButtonWithStatus
                              onClick={() => handleDeleteContent(job.id)}
                              className="delete-button"
                              disabled={jobDetailsMap.get(job.id).job.detailed_workflow_state === WorkflowState.FETCHING_HTML ||
                                       jobDetailsMap.get(job.id).job.detailed_workflow_state === WorkflowState.FETCHING_VIDEO ||
                                       jobDetailsMap.get(job.id).job.detailed_workflow_state === WorkflowState.GENERATING_CLIPS}
                              isLoading={!!loadingStates[`delete-${job.id}`]}
                              loadingText={loadingStates[`delete-${job.id}`]}
                            >
                              Delete Content
                            </ButtonWithStatus>
                          )}
                        </div>
                      )}

                      {editingContentId === job.id && (
                        <ContentEditor
                          jobId={job.id}
                          jobDetails={jobDetailsMap.get(job.id)}
                          onClose={() => setEditingContentId(null)}
                          onUpdate={(jobId) => onJobDetailsUpdate(jobId)}
                          getToken={getToken}
                          setError={setError}
                        />
                      )}
                    </div>
                  </td>
                </tr>
              )}
            </React.Fragment>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default JobTable;
