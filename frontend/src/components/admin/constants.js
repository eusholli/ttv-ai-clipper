// Workflow states that match backend states
export const WorkflowState = {
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
