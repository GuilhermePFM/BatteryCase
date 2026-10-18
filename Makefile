MODEL   := docs/model/model.md
HTML    := docs/model/model.html
PDF     := docs/model/model.pdf

STOCH      := docs/model/model-stochastic.md
STOCH_HTML := docs/model/model-stochastic.html
STOCH_PDF  := docs/model/model-stochastic.pdf

PANDOC_FLAGS := --standalone --metadata pagetitle="Battery dispatch model"
STOCH_FLAGS  := --standalone --metadata pagetitle="Battery dispatch under stochastic prices"

.PHONY: html preview pdf html-stochastic preview-stochastic pdf-stochastic clean-docs

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

## The same three targets for the stochastic formulation
html-stochastic: $(STOCH_HTML)

$(STOCH_HTML): $(STOCH)
	pandoc $< -o $@ $(STOCH_FLAGS) --mathjax

preview-stochastic: $(STOCH_HTML)
	setsid -f xdg-open "$(abspath $(STOCH_HTML))"

pdf-stochastic: $(STOCH_PDF)

$(STOCH_PDF): $(STOCH)
	pandoc $< -o $@ $(STOCH_FLAGS) --toc --pdf-engine=tectonic

clean-docs:
	rm -f $(HTML) $(PDF) $(STOCH_HTML) $(STOCH_PDF)
