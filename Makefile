MODEL   := docs/model/model.md
HTML    := docs/model/model.html
PDF     := docs/model/model.pdf

STOCH      := docs/model/model-stochastic.md
STOCH_HTML := docs/model/model-stochastic.html
STOCH_PDF  := docs/model/model-stochastic.pdf

BOTH_PDF   := docs/model/battery-dispatch.pdf

LATEX_DIR  := docs/model/latex
FIGURES    := docs/model/figures/cutting-plane.png

## Image paths in the notes are relative to the note, as GitHub reads them;
## pandoc resolves them against the working directory unless told otherwise.
RESOURCES    := --resource-path=docs/model
PANDOC_FLAGS := --standalone $(RESOURCES) --metadata pagetitle="Battery dispatch model"
STOCH_FLAGS  := --standalone $(RESOURCES) --metadata pagetitle="Battery dispatch under stochastic prices"

## PDFs go through LaTeX as articles: pandoc's default template, a typographic
## preamble, and a Lua filter that turns a Markdown note into an article body
## (drops the title heading and the manual section numbers, which LaTeX then
## assigns itself, so the "§4.2" references in the prose still match).
## The stochastic note draws its scenario tree with box-drawing characters,
## which Latin Modern Mono does not carry. Use a Unicode mono font when the
## machine has one; without it the build still succeeds, with a warning and a
## few missing glyphs in that one code block.
MONOFONT := $(shell fc-list : family 2>/dev/null | tr ',' '\n' | grep -ixm1 'Noto Sans Mono')
MONO_OPT := $(if $(MONOFONT),-V monofont="$(MONOFONT)")

ARTICLE_DEPS := $(LATEX_DIR)/common.yaml $(LATEX_DIR)/preamble.tex $(LATEX_DIR)/article.lua
PANDOC_ARTICLE := pandoc --standalone --pdf-engine=tectonic $(RESOURCES) \
	--metadata-file=$(LATEX_DIR)/common.yaml \
	--include-in-header=$(LATEX_DIR)/preamble.tex \
	--lua-filter=$(LATEX_DIR)/article.lua \
	--metadata date="$(shell LC_ALL=C date +'%e %B %Y' | sed 's/^ //')" \
	$(MONO_OPT)

.PHONY: docker docker-shell docker-test results results-quick results-list figures html preview pdf pdfs pdf-combined html-stochastic preview-stochastic pdf-stochastic clean-docs

## Run the model in Docker: same pinned environment on any machine, results
## written to data/results on the host. Extra arguments pass through, e.g.
## `make docker ARGS="dispatch --start 2018-01-01 --end 2018-01-31"`.
ARGS ?=

docker:
	scripts/docker-run.sh $(ARGS)

docker-shell:
	DEV=1 scripts/docker-run.sh --shell

## The test suite inside the image, which is what "it runs anywhere" means.
## The cache goes to /tmp: /app belongs to root, and the run does not.
docker-test:
	DEV=1 scripts/docker-run.sh --shell -c "pytest -o cache_dir=/tmp/pytest_cache"

## Re-run every measurement the documents quote: the headline dispatch, the
## two search methods over every horizon, the tolerance table, and the one-shot
## MILPs behind tractability.md. About two hours; `results-quick` walks the same
## path over short horizons, writing under data/results/reproduce/quick/.
results:
	uv run python scripts/reproduce_docs.py

results-quick:
	uv run python scripts/reproduce_docs.py --quick

results-list:
	uv run python scripts/reproduce_docs.py --list

## Redraw the figures the notes embed
figures: $(FIGURES)

docs/model/figures/cutting-plane.png: scripts/plot_cutting_plane.py
	uv run python $<

## Render the model doc to HTML (MathJax, same engine GitHub uses)
html: $(HTML)

$(HTML): $(MODEL) $(FIGURES)
	pandoc $< -o $@ $(PANDOC_FLAGS) --mathjax

## Render and open in the browser; afterwards `make html` + refresh is enough
## setsid -f detaches the viewer: xdg-open blocks until the browser exits, and
## a bare `&` would be killed when the task shell tears down its process group.
preview: $(HTML)
	setsid -f xdg-open "$(abspath $(HTML))"

## Export a PDF, typeset as a LaTeX article (requires tectonic)
pdf: $(PDF)

$(PDF): $(MODEL) $(FIGURES) $(ARTICLE_DEPS) docs/model/latex/model.yaml
	$(PANDOC_ARTICLE) --metadata-file=docs/model/latex/model.yaml $< -o $@

## The same three targets for the stochastic formulation
html-stochastic: $(STOCH_HTML)

$(STOCH_HTML): $(STOCH)
	pandoc $< -o $@ $(STOCH_FLAGS) --mathjax

preview-stochastic: $(STOCH_HTML)
	setsid -f xdg-open "$(abspath $(STOCH_HTML))"

pdf-stochastic: $(STOCH_PDF)

$(STOCH_PDF): $(STOCH) $(ARTICLE_DEPS) docs/model/latex/model-stochastic.yaml
	$(PANDOC_ARTICLE) --metadata-file=docs/model/latex/model-stochastic.yaml $< -o $@

## Both notes in one article, each as a numbered part
pdf-combined: $(BOTH_PDF)

$(BOTH_PDF): $(MODEL) $(STOCH) $(FIGURES) $(ARTICLE_DEPS) docs/model/latex/combined.yaml
	$(PANDOC_ARTICLE) --metadata-file=docs/model/latex/combined.yaml \
	  --top-level-division=part $(MODEL) $(STOCH) -o $@

## Every PDF: the two notes separately and the two of them together
pdfs: pdf pdf-stochastic pdf-combined

clean-docs:
	rm -f $(HTML) $(PDF) $(STOCH_HTML) $(STOCH_PDF) $(BOTH_PDF)
