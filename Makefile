MODEL   := docs/model/model.md
HTML    := docs/model/model.html
PDF     := docs/model/model.pdf

PANDOC_FLAGS := --standalone --metadata pagetitle="Battery dispatch model"

.PHONY: html preview pdf clean-docs

## Render the model doc to HTML (MathJax, same engine GitHub uses)
html: $(HTML)

$(HTML): $(MODEL)
	pandoc $< -o $@ $(PANDOC_FLAGS) --mathjax

## Render and open in the browser; afterwards `make html` + refresh is enough
## setsid -f detaches the viewer: xdg-open blocks until the browser exits, and
## a bare `&` would be killed when the task shell tears down its process group.
preview: $(HTML)
	setsid -f xdg-open "$(abspath $(HTML))"

## Export a PDF (requires tectonic)
pdf: $(PDF)

$(PDF): $(MODEL)
	pandoc $< -o $@ $(PANDOC_FLAGS) --toc --pdf-engine=tectonic

clean-docs:
	rm -f $(HTML) $(PDF)
