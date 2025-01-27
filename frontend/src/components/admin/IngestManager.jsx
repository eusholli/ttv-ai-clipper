import { useState, useEffect } from 'react';
import { useAuth } from '@clerk/clerk-react';
import { fetchJobs, fetchJobDetails, deleteArchive } from './api';
import JobForm from './components/JobForm';
import JobTable from './components/JobTable';
import LogViewer from './components/LogViewer';
import ButtonWithStatus from './components/ButtonWithStatus';
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

  // Fetch jobs and handle polling
  useEffect(() => {
    let interval;
    
    const checkAndUpdateJobs = async () => {
      const currentJobs = await fetchJobs(getToken);
      setJobs(currentJobs);
      
      const activeJobs = currentJobs.filter(job => 
        job.status !== 'completed' && job.status !== 'failed' && job.status !== 'deleted' && job.status !== 'waiting'
      );
      
      // Update details for both active and expanded jobs
      const jobsToUpdate = new Set([
        ...Array.from(expandedJobs),
        ...activeJobs.map(job => job.id)
      ]);
      jobsToUpdate.forEach(jobId => {
        handleJobDetailsUpdate(jobId);
      });
      
      return activeJobs.length > 0;
    };

    const startPolling = () => {
      // Clear any existing interval
      if (interval) {
        clearInterval(interval);
      }
      
      // Start new polling interval
      interval = setInterval(async () => {
        const hasActiveJobs = await checkAndUpdateJobs();
        if (!hasActiveJobs) {
          clearInterval(interval);
          interval = null;
        }
      }, 1000);
    };

    // Handle job status changes
    const handleJobStatusChange = async () => {
      const hasActiveJobs = await checkAndUpdateJobs();
      if (hasActiveJobs) {
        startPolling();
      }
    };

    // Initial setup
    checkAndUpdateJobs().then(hasActiveJobs => {
      if (hasActiveJobs) {
        startPolling();
      }
    });

    // Set up event listener
    window.addEventListener('jobStatusChanged', handleJobStatusChange);

    // Cleanup
    return () => {
      if (interval) {
        clearInterval(interval);
      }
      window.removeEventListener('jobStatusChanged', handleJobStatusChange);
    };
  }, [expandedJobs, getToken]); // Re-run when expandedJobs or getToken changes

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

        // Update job details for any expanded jobs that still exist
        const remainingExpandedJobs = Array.from(expandedJobs).filter(jobId => 
          currentJobs.some(job => job.id === jobId)
        );
        remainingExpandedJobs.forEach(jobId => {
          handleJobDetailsUpdate(jobId);
        });

        // Update expandedJobs to remove any deleted jobs
        setExpandedJobs(new Set(remainingExpandedJobs));

        if (currentArchivedCount === 0) {
          clearInterval(pollInterval);
          setArchiveDeleteStatus('idle');
          setArchiveDeleteProgress(0);
          
          // Dispatch event to ensure any remaining jobs are properly refreshed
          const event = new CustomEvent('jobStatusChanged');
          window.dispatchEvent(event);
        }

        remainingJobs = currentArchivedCount;
      }, 1000);

      // Safety cleanup after 30 seconds
      setTimeout(() => {
        if (pollInterval) {
          clearInterval(pollInterval);
          setArchiveDeleteStatus('idle');
          setArchiveDeleteProgress(0);
          
          // Final refresh to ensure UI is in sync
          const event = new CustomEvent('jobStatusChanged');
          window.dispatchEvent(event);
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
          <ButtonWithStatus
            onClick={handleDeleteArchive}
            className="delete-button"
            disabled={archiveDeleteStatus !== 'idle'}
            isLoading={archiveDeleteStatus !== 'idle'}
            loadingText={
              archiveDeleteStatus === 'deleting' ? 'Initiating Deletion...' :
              archiveDeleteStatus === 'polling' ? `Deleting Archive (${archiveDeleteProgress}%)` :
              'Processing...'
            }
          >
            Delete Archive Jobs
          </ButtonWithStatus>
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
