// n8n Code node; mode: Run Once for All Items.
const output = [];
const sectionPattern = /^(?:ပုဒ်မ\s*)?([၀-၉0-9]{1,4})(?:\s*[။.]|\s+|$)(.*)$/u;
const chapterPattern = /^(အခန်း\s*\([^\n]+\)|အခန်း\s+[၀-၉0-9]+|chapter\s+[^\n]+)$/iu;
const subsectionPattern = /^\s*[\(（]([က-အ၀-၉0-9]+)[\)）]\s*(.*)$/u;

function splitBySubsection(section) {
  const parts = [];
  let current = null;

  for (let lineIndex = 0; lineIndex < section.lines.length; lineIndex++) {
    const line = section.lines[lineIndex];
    // A subsection can start immediately after the section number on its first line.
    const candidate = lineIndex === 0 && section.section
      ? (line.match(sectionPattern)?.[2] || '')
      : line;
    const match = candidate.match(subsectionPattern);

    if (match) {
      if (current) parts.push(current);
      current = { subsection: match[1], lines: [line] };
    } else if (current) {
      current.lines.push(line);
    } else {
      current = { subsection: null, lines: [line] };
    }
  }

  if (current) parts.push(current);
  return parts;
}

for (let itemIndex = 0; itemIndex < items.length; itemIndex++) {
  const input = items[itemIndex].json;
  const text = String(input.text || '')
    .replace(/\r\n/g, '\n')
    .replace(/[\t ]+/g, ' ')
    .replace(/\n{3,}/g, '\n\n')
    .trim();

  if (!text) throw new Error('No extracted text was supplied');

  const lines = text.split('\n').map((value) => value.trim()).filter(Boolean);
  const sections = [];
  let currentSection = null;
  let currentChapter = null;

  for (const line of lines) {
    if (chapterPattern.test(line)) {
      currentChapter = line;
      continue;
    }

    const sectionMatch = line.match(sectionPattern);
    if (sectionMatch) {
      if (currentSection) sections.push(currentSection);
      currentSection = {
        chapter: currentChapter,
        section: sectionMatch[1],
        lines: [line],
      };
    } else if (currentSection) {
      currentSection.lines.push(line);
    } else {
      currentSection = { chapter: currentChapter, section: null, lines: [line] };
    }
  }

  if (currentSection) sections.push(currentSection);

  const maxLength = 5000;
  const overlap = 500;
  let chunkIndex = 0;

  for (const section of sections) {
    for (const part of splitBySubsection(section)) {
      const body = part.lines.join('\n');
      for (let start = 0; start < body.length; start += maxLength - overlap) {
        const content = body.slice(start, start + maxLength).trim();
        if (!content) continue;

        output.push({
          json: {
            document_id: input.document_id,
            chunk_index: chunkIndex++,
            chapter: section.chapter,
            section: section.section,
            subsection: part.subsection,
            content,
            metadata: {
              law_name: input.law_name,
              law_number: input.law_number || null,
              language: input.language || 'my',
              category: input.category || null,
              source_url: input.source_url,
              source_file_name: input.source_file_name || input.filename || null,
            },
          },
          pairedItem: { item: itemIndex },
        });

        if (body.length <= maxLength) break;
      }
    }
  }
}

return output;
