import React, { useState } from 'react';
import { WorkflowState } from '../constants';
import { getStatusColor, formatWorkflowState, formatDate, getWorkflowStepClass } from '../utils';
import { fetchJobLog, deleteContent, processTranscript } from '../api';
import ContentEditor from './ContentEditor';

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

  const handleProcessTranscript = async (jobId) => {
    try {
      await processTranscript(jobId, getToken);
      await onJobDetailsUpdate(jobId);
    } catch (err) {
      setError(err.message);
    }
  };

  const handleDeleteContent = async (jobId) => {
    if (!window.confirm('Are you sure you want to delete all content for this job? This cannot be undone.')) {
      return;
    }

    try {
      await deleteContent(jobId, getToken);
      await onJobDetailsUpdate(jobId);
    } catch (err) {
      setError(err.message);
    }
  };

  const handleLogView = async (jobId) => {
    try {
      const data = await fetchJobLog(jobId, getToken);
      onLogFetched(data.log);
    } catch (err) {
      setError(err.message);
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
                  <button onClick={() => handleLogView(job.id)}>View Log</button>
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
                            <button 
                              onClick={() => setEditingContentId(job.id)}
                              disabled={jobDetailsMap.get(job.id).job.detailed_workflow_state === WorkflowState.FETCHING_HTML || 
                                       jobDetailsMap.get(job.id).job.detailed_workflow_state === WorkflowState.FAILED && !jobDetailsMap.get(job.id).job.html_fetch_success}
                            >
                              Edit Content
                            </button>
                            <button
                              onClick={() => handleProcessTranscript(job.id)}
                              disabled={!jobDetailsMap.get(job.id).job.transcript}
                            >
                              Process Transcript
                            </button>
                          </>
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
