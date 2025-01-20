import { WorkflowState } from './constants';

export const getStatusColor = (status) => {
  switch (status) {
    case 'completed': return 'status-completed';
    case 'failed': return 'status-failed';
    case 'running': return 'status-running';
    case 'deleted': return 'status-deleted';
    case 'waiting': return 'status-waiting';
    default: return 'status-pending';
  }
};

export const formatWorkflowState = (state) => {
  if (!state) return '';
  return state.split('_').map(word => 
    word.charAt(0).toUpperCase() + word.slice(1).toLowerCase()
  ).join(' ');
};

export const formatDate = (dateString) => {
  return new Date(dateString).toLocaleString();
};

export const getWorkflowStepClass = (jobDetails, step) => {
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
