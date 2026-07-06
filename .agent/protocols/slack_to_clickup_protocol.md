# Protocol: Slack-to-ClickUp Ticket Creation

This protocol defines the mandatory communication steps when a Slack thread leads to the creation of a ClickUp ticket.

> [!IMPORTANT]
> **Work Exception**: All WORK tasks will NEVER need to connect to clickup. Document Work tasks in the repository (Dashboard, Todo, Backlogs) and notify via Slack only.

## Workflow Steps

1.  **Extract Information**: Gather all requirements, images, and context from the Slack thread and its replies.
2.  **Create ClickUp Task**: Use the `clickup_client.py` script to create the task in the appropriate list.
3.  **Confirm in Slack**: Reply to the Slack thread with the following:
    *   **Mention Thread Starter**: `@username` (the person who started the thread).
    *   **Mention User**: `@you` (the requester).
    *   **ClickUp Link**: Provide the direct link to the created task.
    *   **Mention Relevant Engineer**: Assign/mention the specific engineer based on the project category.

## Engineer Mapping

| Project Category | Lead Engineer | Slack Mention |
| :--- | :--- | :--- |
| `gogogo`, `esim`, `travel`, `safaraya` | Teammate Afnandika | `@Teammate Afnandika` |
| `ops platform`, `bangkokok`, `yellow`, `AI` | Teammate | `@Teammate` |

## Example Reply
> "Ticket created for the eSIM UI issue: [ClickUp Task Link]
> 
> CC: @thread_starter @you
> FYI: @Teammate Afnandika"
