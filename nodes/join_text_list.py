"""JoinTextList — Combine a list of strings (or a single string) into one text."""


class JoinTextList:
    """Join multiple text strings into one. Handles both list and single string inputs.

    Useful after batch-processing nodes (like Florence2) that return a list of
    strings when given a batch of images.
    """

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "text": ("STRING", {"forceInput": True}),
                "separator": ("STRING", {"default": ", ", "multiline": False}),
                "deduplicate": ("BOOLEAN", {"default": True}),
            },
        }

    RETURN_TYPES = ("STRING",)
    FUNCTION = "execute"
    CATEGORY = "text"
    INPUT_IS_LIST = True

    def execute(self, text, separator, deduplicate):
        sep = separator[0] if isinstance(separator, list) else separator
        dedup = deduplicate[0] if isinstance(deduplicate, list) else deduplicate

        # Flatten: text may be a list of strings, a list of lists, or a single string
        flat = []
        for item in (text if isinstance(text, list) else [text]):
            if isinstance(item, list):
                flat.extend(str(s) for s in item)
            else:
                flat.append(str(item))

        if dedup:
            seen = set()
            unique = []
            for s in flat:
                # Deduplicate by splitting on separator and removing duplicate phrases
                parts = [p.strip() for p in s.split(sep) if p.strip()]
                for p in parts:
                    if p.lower() not in seen:
                        seen.add(p.lower())
                        unique.append(p)
            result = sep.join(unique)
        else:
            result = sep.join(flat)

        return (result,)
