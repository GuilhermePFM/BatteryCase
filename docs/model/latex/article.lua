--- Turn a GitHub-flavoured Markdown note into the body of a LaTeX article.
---
--- Four things that are right in Markdown are wrong in an article:
---   * the leading level-1 heading repeats the title page;
---   * headings carry their own section numbers, which LaTeX assigns itself
---     (the manual numbers match the order, so references like "§4.2" survive);
---   * the `---` rules and the closing "Reading and rendering" section exist
---     only for the Markdown reader;
---   * links to sibling `.md` files resolve to nothing in a PDF.
---
--- Metadata flag `promote-title`: true for a standalone article, where the
--- level-1 heading is dropped and everything below it moves up one level;
--- false when several notes are concatenated and each keeps its own part.

local promote_title = true

local function meta_flag(meta)
  if meta['promote-title'] ~= nil then
    promote_title = meta['promote-title'] == true
      or pandoc.utils.stringify(meta['promote-title']) == 'true'
  end
  return meta
end

-- "4.1 Storage bounds" -> "Storage bounds"; also "4." and "4.1.".
-- Lua patterns are bytewise, so the number is matched on its own: a literal
-- "§" is two bytes and would not survive a `?` quantifier.
local function strip_number(inlines)
  local first = inlines[1]
  if first and first.t == 'Str'
     and first.text:match('^%d+%.?%d*%.?$') then
    table.remove(inlines, 1)
    while inlines[1] and inlines[1].t == 'Space' do table.remove(inlines, 1) end
  end
  return inlines
end

local dropped_h1 = false

local function header(el)
  if el.level == 1 and promote_title and not dropped_h1 then
    dropped_h1 = true
    return {}
  end
  el.content = strip_number(el.content)
  if promote_title and el.level > 1 then el.level = el.level - 1 end
  return el
end

local function link(el)
  -- Keep real URLs; a relative .md path becomes its own text.
  if el.target:match('^%a+:') then return nil end
  if el.target:match('%.md') or el.target:match('^#') then return el.content end
  return nil
end

-- Drop the closing "Reading and rendering this document" section: the heading
-- and every block under it, up to the next heading of the same or higher level.
local function drop_rendering_section(doc)
  local out, skipping, at_level = {}, false, nil
  for _, block in ipairs(doc.blocks) do
    if block.t == 'Header' then
      local text = pandoc.utils.stringify(block.content):lower()
      if text:match('reading and rendering') then
        skipping, at_level = true, block.level
        goto continue
      elseif skipping and block.level <= at_level then
        skipping = false
      end
    end
    if not skipping then table.insert(out, block) end
    ::continue::
  end
  doc.blocks = out
  return doc
end

-- Pipe tables carry no widths, so pandoc gives every column the same share of
-- the line and the long "Meaning" column wraps to a sliver. Size each column
-- by the longest cell it holds instead, with a floor so a column of symbols
-- still gets room, and a ceiling so one long sentence cannot take the page.
local function size_columns(tbl)
  local widths, ncols = {}, #tbl.colspecs
  local function scan(rows)
    for _, row in ipairs(rows) do
      for i, cell in ipairs(row.cells) do
        local n = #pandoc.utils.stringify(cell.contents)
        widths[i] = math.max(widths[i] or 0, math.min(n, 60))
      end
    end
  end
  scan(tbl.head.rows)
  for _, body in ipairs(tbl.bodies) do scan(body.body) end

  local total = 0
  for i = 1, ncols do
    widths[i] = math.max(widths[i] or 1, 6) + 3  -- a little padding
    total = total + widths[i]
  end
  for i = 1, ncols do
    tbl.colspecs[i][2] = 0.96 * widths[i] / total
  end
  return tbl
end

return {
  { Meta = meta_flag },
  { Pandoc = drop_rendering_section },
  { HorizontalRule = function() return {} end },
  { Header = header, Link = link, Table = size_columns },
}
