## Type Context: Unknown / General Document

The type of this file could not be determined from its location or name. It could be a research paper, to-do list, specification, meeting notes, changelog, API documentation, or any other structured document.

Adapt your analysis to whatever the content appears to be, but focus on these universal qualities:

- **Internal consistency**: Does the document contradict itself? Look for statements in one section that conflict with another.
- **Structure over prose**: Dense paragraphs without headers or bullets are harder for both humans and LLMs to parse. If the file is >50 lines of unbroken text, suggest adding structure.
- **Actionability**: If this document is meant to guide behavior, are the instructions concrete enough to follow? Vague guidance produces no observable change in agent behavior.
- **Freshness signals**: Are there dates, version numbers, file paths, or tool references that may be outdated? Flag anything that looks stale.
- **Audience fit**: Is the level of detail appropriate? A document used as always-on context should be concise. A reference document read on-demand can be longer.
