# Document Review and Delivery Protocol

To ensure high quality and user alignment, all new documentation or significant updates to existing documentation MUST follow this 3-step process.

## 1. Research and Planning
*   Gather all necessary context from local files, Google Drive, and Slack.
*   Create an `implementation_plan.md` artifact detailing the proposed structure and key content.
*   Obtain user approval on the plan via `notify_user`.

## 2. Artifact Drafting and Review
*   **DO NOT** create the final `.md` file in the repository yet.
*   Create a "Review Artifact" (e.g., `content_review.md` or a specific file name in the `brain/` directory) containing the **full content** of the proposed document.
*   Notify the user and wait for explicit feedback or approval on the content artifact.
*   Iterate on the artifact based on feedback until approved.

## 3. Implementation and Delivery
*   Once approved, create the final `.md` file in the appropriate repository location.
*   **Google Drive Upload**: If the document is for a client (Work or the secondary client), upload the finalized document to the relevant Google Drive using the appropriate skill (`work-drive-connector` or `secondary-drive-connector`).
*   Include the Google Drive link in the final repository file and the `walkthrough.md`.

## Summary of Sequence
`Plan Artifact` (Approved) -> `Content Artifact` (Approved) -> `Repo File` + `GDrive Upload`
