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
  FAILED: "failed",
  DELETED: "deleted"
};

// Required metadata fields for transcript
export const RequiredMetadataFields = {
  TITLE: "title",
  DATE: "date",
  YOUTUBE_ID: "youtube_id"
};

// Transcript structure validation
export const TranscriptValidation = {
  // Metadata validation
  metadata: {
    required: [RequiredMetadataFields.TITLE, RequiredMetadataFields.DATE, RequiredMetadataFields.YOUTUBE_ID],
    dateFormats: ["YYYY-MM-DD", "MMM DD, YYYY"]
  },
  // Segment validation
  segment: {
    required: ["speaker", "company", "start_timestamp", "end_timestamp"],
    defaults: {
      speaker: "Unknown",
      company: "Unknown",
      subjects: [],
      download: null
    }
  }
};
