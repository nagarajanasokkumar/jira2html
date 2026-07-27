"""
attachment_handler.py
---------------------
Downloads Jira attachments and encodes them for embedding in self-contained HTML.
- Images → Base64 data URIs (inline display)
- All other files → Base64 data URIs (downloadable links)
- Respects max_attachment_size_mb limit from config
"""

import base64
import logging
import mimetypes
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

# Mime types considered images (rendered inline)
IMAGE_MIME_TYPES = {
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/gif",
    "image/webp",
    "image/svg+xml",
    "image/bmp",
    "image/tiff",
}


def get_mime_type(filename: str, content_type: Optional[str] = None) -> str:
    """Determine MIME type from content_type header or filename extension."""
    if content_type and content_type != "application/octet-stream":
        return content_type.split(";")[0].strip()
    guessed, _ = mimetypes.guess_type(filename)
    return guessed or "application/octet-stream"


def encode_attachment(content: bytes, mime_type: str) -> str:
    """Encode raw bytes as a Base64 data URI string."""
    b64 = base64.b64encode(content).decode("utf-8")
    return f"data:{mime_type};base64,{b64}"


def is_image(mime_type: str) -> bool:
    return mime_type.lower() in IMAGE_MIME_TYPES


class AttachmentHandler:
    """
    Downloads and encodes Jira attachments for HTML embedding.
    Uses a thread pool for concurrent downloads.
    """

    def __init__(self, jira_client, config: dict):
        self.client = jira_client
        opts = config.get("options", {})
        self.embed_attachments = opts.get("embed_attachments", True)
        self.max_size_bytes = opts.get("max_attachment_size_mb", 10) * 1024 * 1024
        self.workers = opts.get("attachment_workers", 3)

    def process_attachments(self, attachments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Process a list of Jira attachment metadata dicts.
        Returns enriched list with 'data_uri', 'is_image', 'mime_type' added.
        Downloads are performed concurrently.
        """
        if not self.embed_attachments or not attachments:
            return attachments

        results: List[Dict[str, Any]] = list(attachments)  # pre-fill with originals

        def download_one(idx: int, att: Dict[str, Any]) -> tuple:
            return idx, self._process_single(att)

        with ThreadPoolExecutor(max_workers=self.workers) as executor:
            futures = {
                executor.submit(download_one, i, att): i
                for i, att in enumerate(attachments)
            }
            for future in as_completed(futures):
                try:
                    idx, processed = future.result()
                    results[idx] = processed
                except Exception as e:
                    idx = futures[future]
                    logger.error(f"Failed to process attachment [{idx}]: {e}")
                    # results[idx] already holds the original metadata

        return results

    def _process_single(self, att: Dict[str, Any]) -> Dict[str, Any]:
        """Download and encode a single attachment."""
        result = dict(att)  # copy original metadata

        filename = att.get("filename", "unknown")
        content_url = att.get("content", "")
        size_bytes = att.get("size", 0)
        content_type = att.get("mimeType", "")

        mime_type = get_mime_type(filename, content_type)
        result["mime_type"] = mime_type
        result["is_image"] = is_image(mime_type)
        result["data_uri"] = None
        result["skipped"] = False
        result["skip_reason"] = None

        if not content_url:
            result["skipped"] = True
            result["skip_reason"] = "No content URL"
            logger.warning(f"Attachment '{filename}' has no content URL — skipping.")
            return result

        if size_bytes > self.max_size_bytes:
            result["skipped"] = True
            result["skip_reason"] = f"File size {size_bytes / 1024 / 1024:.1f} MB exceeds limit of {self.max_size_bytes / 1024 / 1024:.0f} MB"
            logger.warning(
                f"Attachment '{filename}' ({size_bytes / 1024 / 1024:.1f} MB) "
                f"exceeds max size limit — skipping embed."
            )
            return result

        try:
            logger.debug(f"Downloading attachment: {filename} ({size_bytes} bytes)")
            content = self.client.get_attachment_content(content_url)
            result["data_uri"] = encode_attachment(content, mime_type)
            logger.debug(f"Embedded attachment: {filename}")
        except Exception as e:
            result["skipped"] = True
            result["skip_reason"] = f"Download error: {str(e)}"
            logger.error(f"Could not download attachment '{filename}': {e}")

        return result

    def get_display_size(self, size_bytes: int) -> str:
        """Human-readable file size."""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        else:
            return f"{size_bytes / 1024 / 1024:.1f} MB"
