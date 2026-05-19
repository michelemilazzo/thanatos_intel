class OCRService:
    """Runtime OCR abstraction layer."""

    def extract(self, document_type, source=None):
        return {
            'document_type': document_type,
            'fields': {},
            'confidence': 0.0,
            'missing_fields': [],
            'provider': 'runtime_placeholder'
        }
