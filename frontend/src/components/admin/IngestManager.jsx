import { useState, useEffect } from 'react';
import { useAuth } from '@clerk/clerk-react';
import { fetchJobs, fetchJobDetails, deleteArchive } from './api';
import JobForm from './components/JobForm';
import JobTable from './components/JobTable';
import LogViewer from './components/LogViewer';
import './IngestManager.css';

const IngestManager = () => {
  const { getToken } = useAuth();
  const [jobs, setJobs] = useState([]);
  const [error, setError] = useState(null);
  const [expandedJobs, setExpandedJobs] = useState(new Set());
  const [jobDetailsMap, setJobDetailsMap] = useState(new Map());
  const [showLog, setShowLog] = useState(false);
  const [logContent, setLogContent] = useState('');
  const [archiveDeleteStatus, setArchiveDeleteStatus] = useState('idle');
  const [archiveDeleteProgress, setArchiveDeleteProgress] = useState(0);

  // Fetch jobs and set up polling if needed
  useEffect(() => {
    let interval;
    
    const pollIfNeeded = async () => {
      const currentJobs = await fetchJobs(getToken);
      setJobs(currentJobs);
      
      const activeJobs = currentJobs.filter(job => 
        job.status !== 'completed' && job.status !== 'failed' && job.status !== 'deleted' && job.status !== 'waiting'
      );
      
      // If there are active jobs, start polling
      if (activeJobs.length > 0) {
        // Clear any existing interval before setting a new one
        if (interval) {
          clearInterval(interval);
        }
        
        interval = setInterval(async () => {
          const updatedJobs = await fetchJobs(getToken);
          setJobs(updatedJobs);
          
          const stillActive = updatedJobs.filter(job => 
            job.status !== 'completed' && job.status !== 'failed' && job.status !== 'deleted' && job.status !== 'waiting'
          );
          
          // If no more active jobs, clear the interval
          if (stillActive.length === 0) {
            clearInterval(interval);
            interval = null;
          } else {
            // Update details for expanded jobs using current expandedJobs state
            expandedJobs.forEach(jobId => {
              handleJobDetailsUpdate(jobId);
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
        handleJobDetailsUpdate(jobId);
      }
    });
  }, [expandedJobs]);

  const handleJobDetailsUpdate = async (jobId) => {
    try {
      const data = await fetchJobDetails(jobId, getToken);
      setJobDetailsMap(prev => new Map(prev).set(jobId, data));
    } catch (err) {
      console.error('Error fetching job details:', err);
      setError('Failed to fetch job details');
    }
  };

  const handleJobCreated = (newJob) => {
    setJobs(prevJobs => [newJob, ...prevJobs]);
    setExpandedJobs(prev => new Set(prev).add(newJob.id));
    handleJobDetailsUpdate(newJob.id);
  };

  const handleDeleteArchive = async () => {
    if (!window.confirm('Are you sure you want to delete all archived jobs? This cannot be undone.')) {
      return;
    }

    setArchiveDeleteStatus('deleting');
    setError(null);

    try {
      // Get initial count of archived jobs
      const initialJobs = await fetchJobs(getToken);
      const initialArchivedCount = initialJobs.filter(job => 
        job.status === 'completed' || job.status === 'failed' || job.status === 'deleted'
      ).length;

      if (initialArchivedCount === 0) {
        setArchiveDeleteStatus('idle');
        return;
      }

      // Start deletion
      const data = await deleteArchive(getToken);
      console.log(`Deleting ${data.deleted_jobs} archived jobs`);

      // Start polling to check progress
      setArchiveDeleteStatus('polling');
      let remainingJobs = initialArchivedCount;
      
      const pollInterval = setInterval(async () => {
        const currentJobs = await fetchJobs(getToken);
        setJobs(currentJobs);
        
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

  return (
    <div className="ingest-manager">
      <h1>Content Ingest Manager</h1>
      
      <JobForm 
        onJobCreated={handleJobCreated}
        setError={setError}
        getToken={getToken}
      />

      {error && <div className="error-message">{error}</div>}

      {/* Active Jobs Table */}
      <JobTable
        jobs={jobs.filter(job => 
          job.status !== 'completed' && job.status !== 'failed' && job.status !== 'deleted'
        )}
        title="Active Jobs"
        expandedJobs={expandedJobs}
        setExpandedJobs={setExpandedJobs}
        jobDetailsMap={jobDetailsMap}
        onJobDetailsUpdate={handleJobDetailsUpdate}
        getToken={getToken}
        setError={setError}
        onLogFetched={(log) => {
          setLogContent(log);
          setShowLog(true);
        }}
      />

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
        <JobTable
          jobs={jobs.filter(job => 
            job.status === 'completed' || job.status === 'failed' || job.status === 'deleted'
          )}
          title=""
          expandedJobs={expandedJobs}
          setExpandedJobs={setExpandedJobs}
          jobDetailsMap={jobDetailsMap}
          onJobDetailsUpdate={handleJobDetailsUpdate}
          getToken={getToken}
          setError={setError}
          onLogFetched={(log) => {
            setLogContent(log);
            setShowLog(true);
          }}
        />
      </div>

      {showLog && (
        <LogViewer
          logContent={logContent}
          onClose={() => setShowLog(false)}
        />
      )}
    </div>
  );
};

export default IngestManager;
