export const VENDOR_STATUSES = [
  "NEW",
  "RESEARCHED",
  "READY_TO_CONTACT",
  "CONTACTED",
  "REPLIED",
  "AI_CONVERSATION",
  "INTERESTED",
  "QUALIFYING",
  "QUALIFIED",
  "MEETING_REQUESTED",
  "WAITING_FOR_HUMAN_LINK",
  "MEETING_LINK_RECEIVED",
  "INVITATION_SENT",
  "MEETING_SCHEDULED",
  "HUMAN_HANDOFF",
  "OPTED_OUT",
  "BOUNCED",
] as const;

export const CAMPAIGN_STATUSES = ["DRAFT", "ACTIVE", "PAUSED", "COMPLETED", "ARCHIVED"] as const;

export const CAMPAIGN_ACTIONS = ["activate", "pause", "resume", "archive", "complete"] as const;

export const CONVERSATION_STATUSES = [
  "ACTIVE",
  "HUMAN_CONTROLLED",
  "HUMAN_HANDOFF",
  "WAITING_FOR_HUMAN_LINK",
  "NEEDS_REVIEW",
  "ARCHIVED",
  "CLOSED",
] as const;

export const CONVERSATION_ACTIONS: { action: string; label: string; danger?: boolean }[] = [
  { action: "take_over", label: "Take over" },
  { action: "return_to_ai", label: "Return to AI" },
  { action: "pause_ai", label: "Pause AI" },
  { action: "resume_ai", label: "Resume AI" },
  { action: "request_meeting", label: "Request meeting" },
  { action: "archive", label: "Archive", danger: true },
  { action: "opt_out", label: "Opt out", danger: true },
];

export const JOB_STATUSES = ["PENDING", "CLAIMED", "COMPLETED", "FAILED", "CANCELLED", "PAUSED"] as const;

export const JOB_TYPES = ["INITIAL_EMAIL", "FOLLOW_UP", "AI_REPLY", "MEETING_INVITATION"] as const;

export const MEETING_STATUSES = [
  "REQUESTED",
  "WAITING_FOR_LINK",
  "LINK_RECEIVED",
  "INVITATION_SENT",
  "SCHEDULED",
  "COMPLETED",
  "CANCELLED",
] as const;

export const VENDOR_SOURCES = ["MANUAL", "PASTE", "CSV", "DISCOVERY", "API"] as const;

export const WEEKDAYS: { value: number; label: string }[] = [
  { value: 0, label: "Mon" },
  { value: 1, label: "Tue" },
  { value: 2, label: "Wed" },
  { value: 3, label: "Thu" },
  { value: 4, label: "Fri" },
  { value: 5, label: "Sat" },
  { value: 6, label: "Sun" },
];

export const TIMEZONES = [
  "America/New_York",
  "America/Chicago",
  "America/Denver",
  "America/Los_Angeles",
  "America/Phoenix",
  "Europe/London",
  "Europe/Berlin",
  "Asia/Dubai",
  "Asia/Kolkata",
  "Asia/Singapore",
  "Australia/Sydney",
  "UTC",
];

export const NOTIFICATION_TYPES = [
  "INFO",
  "INTERESTED",
  "QUALIFIED",
  "MEETING_REQUEST",
  "HUMAN_REQUESTED",
  "AI_NEEDS_HELP",
  "ERROR",
  "SYSTEM",
] as const;
