"""
PDF Summarization utility for creating MANUAL entities

This module provides functionality to extract text from PDFs and create
summaries for MANUAL entities.
"""

import hashlib
import base64
from typing import Optional, Dict, Any
from pathlib import Path


def extract_pdf_text(pdf_data: bytes) -> str:
    """
    Extract text content from PDF data.

    Note: This is a simplified implementation. In production, you would use
    libraries like PyPDF2, pdfplumber, or pdfminer for actual PDF text extraction.

    Args:
        pdf_data: Binary PDF data

    Returns:
        Extracted text from the PDF
    """
    # For now, return a placeholder. In production, use a proper PDF library
    # Example with PyPDF2:
    # import PyPDF2
    # from io import BytesIO
    #
    # pdf_file = BytesIO(pdf_data)
    # pdf_reader = PyPDF2.PdfReader(pdf_file)
    # text = ""
    # for page_num in range(len(pdf_reader.pages)):
    #     page = pdf_reader.pages[page_num]
    #     text += page.extract_text()
    # return text

    # Placeholder implementation - returns basic info about the PDF
    return f"PDF Document ({len(pdf_data)} bytes)"


def summarize_text(text: str, max_length: int = 2000) -> str:
    """
    Create a summary of the extracted text.

    Note: This is a simplified implementation. In production, you might use
    NLP libraries or AI models for better summarization.

    Args:
        text: Full text to summarize
        max_length: Maximum length of the summary

    Returns:
        Summarized text
    """
    # Simple truncation-based summarization
    # In production, use proper NLP summarization techniques

    if len(text) <= max_length:
        return text

    # Try to find a good break point
    truncated = text[:max_length]
    last_period = truncated.rfind('.')
    last_newline = truncated.rfind('\n')

    # Use the latest sentence or paragraph break
    break_point = max(last_period, last_newline)
    if break_point > max_length * 0.8:  # Only use if it's not too early
        return truncated[:break_point + 1]

    return truncated + "..."


def create_manual_summary(pdf_data: bytes, filename: str) -> Dict[str, Any]:
    """
    Create a summary for a MANUAL entity from PDF data.

    Args:
        pdf_data: Binary PDF data
        filename: Original filename of the PDF

    Returns:
        Dictionary containing manual metadata and summary
    """
    # Extract text from PDF
    text = extract_pdf_text(pdf_data)

    # Create summary
    summary = summarize_text(text)

    # Generate checksum for the PDF
    checksum = hashlib.sha256(pdf_data).hexdigest()

    # Extract potential metadata from filename
    # Example: "PAR-42MAAUB_Instruction Book.pdf" -> model: PAR-42MAAUB
    parts = filename.replace('.pdf', '').replace('_', ' ').split()
    model_number = None

    for part in parts:
        if any(c.isdigit() for c in part) and len(part) > 3:
            model_number = part
            break

    return {
        "summary": summary,
        "original_filename": filename,
        "file_size": len(pdf_data),
        "checksum": checksum,
        "model_number": model_number,
        "document_type": "instruction_manual" if "instruction" in filename.lower() else "manual"
    }


def link_manual_to_device(manual_metadata: Dict[str, Any], device_name: str) -> Dict[str, Any]:
    """
    Create metadata for linking a manual to a device.

    Args:
        manual_metadata: Metadata from create_manual_summary
        device_name: Name of the device this manual belongs to

    Returns:
        Enhanced metadata with device information
    """
    enhanced = manual_metadata.copy()
    enhanced["device_name"] = device_name
    enhanced["relationship_type"] = "DOCUMENTED_BY"

    return enhanced


def extract_photo_metadata(photo_data: bytes, filename: str) -> Dict[str, Any]:
    """
    Extract metadata from a photo for storage.

    Args:
        photo_data: Binary photo data (JPEG, PNG, etc.)
        filename: Original filename of the photo

    Returns:
        Dictionary containing photo metadata
    """
    # Generate checksum
    checksum = hashlib.sha256(photo_data).hexdigest()

    # Determine photo type from filename
    photo_type = "unknown"
    if "serial" in filename.lower():
        photo_type = "serial_number"
    elif "blower" in filename.lower():
        photo_type = "equipment"
    elif any(x in filename.lower() for x in ["thermostat", "control", "panel"]):
        photo_type = "control_panel"
    else:
        photo_type = "device_photo"

    # Extract file extension
    extension = Path(filename).suffix.lower().replace('.', '')

    return {
        "original_filename": filename,
        "file_size": len(photo_data),
        "checksum": checksum,
        "photo_type": photo_type,
        "format": extension.upper(),
        "mime_type": f"image/{extension}"
    }
