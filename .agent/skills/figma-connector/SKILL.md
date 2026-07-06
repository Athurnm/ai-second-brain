---
name: Figma Connector
description: A skill to interact with Figma API for extracting design data, comments, and images, specifically tailored for PRD generation.
---

# Figma Connector

This skill allows you to interact with Figma files to extract information necessary for creating Product Requirements Documents (PRDs).

## Prerequisites
- **Figma Personal Access Token (PAT):** You must provide a valid Figma PAT.
- **Figma File Key:** The ID of the file you want to access (found in the file URL: `figma.com/file/FILE_KEY/...`).

## Capabilities
1.  **Get File Data:** specific nodes or the entire file.
2.  **Get Comments:** Retrieve discussion on the design.
3.  **Get Images:** Export frames or nodes as images.
4.  **Analyze Frame for PRD:** (High-level) Extract text, hierarchy, and layout structure from a frame to draft a PRD section.

## Usage

### Setup
Ensure you have the `FIGMA_ACCESS_TOKEN` environment variable set or pass it to the scripts.

### Scripts
The core logic is in `scripts/figma_client.py`.

#### List File Comments
```bash
python3 .agent/skills/figma-connector/scripts/figma_client.py get-comments --file-key <FILE_KEY> --token <TOKEN>
```

#### Get File Nodes (for PRD analysis)
```bash
python3 .agent/skills/figma-connector/scripts/figma_client.py get-nodes --file-key <FILE_KEY> --node-ids <NODE_IDS> --token <TOKEN>
```

#### Export Image
```bash
python3 .agent/skills/figma-connector/scripts/figma_client.py export-image --file-key <FILE_KEY> --node-ids <NODE_IDS> --token <TOKEN>
```
