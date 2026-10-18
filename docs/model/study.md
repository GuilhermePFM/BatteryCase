# Study notes: Lagrangian relaxation and the cutting-plane method

Background for [`model.md`](model.md) §6 and
[`model-stochastic.md`](model-stochastic.md) §2.1 and §6. The first states three
properties of the Lagrangian dual and then uses them; this note proves them and
says where each one can fail. The second states a probability space and a
filtration in four lines; §7 here unpacks what they are for and why indexing a
variable by tree node *is* non-anticipativity. The third states the deterministic
equivalent's size in four formulas and defers how the tree is built; §8 derives
the formulas, sets out what a node carries and how the branching rule is
constrained, and finds the affordable tree to be considerably smaller than that
document's own comparison suggests. Nothing here is specific to batteries beyond the running example:
the coupling constraint is the cycle budget $n_{\text{cyc}}(T) \leq \overline{L}$,
the one row of the dispatch model that reaches across every window.

---

## 1. Why relax at all

The dispatch problem decomposes almost perfectly in time. State of charge couples
adjacent periods only, so walking the horizon in windows and handing $S$ forward
loses nothing but foresight. The cycle budget is different: it is a single row
over the whole horizon, and a window cannot know whether a cycle spent today
would have been worth more in a month.

Two ways out, and the choice is the subject of these notes:

- **Split the budget.** Give each window a quota, say $\overline{L} W / T$. This
  keeps feasibility and needs no iteration, but the quota is a guess: a window
  facing exceptional spreads is rationed anyway, and a quiet window's allowance
  is wasted. The split is only right if the guess happens to match the optimum.
- **Price the budget.** Delete the row and charge for its consumption instead.
  Every window then sees the same number $\lambda$, in £ per equivalent full
  cycle, and applies the same myopic rule: *take the trade only if the spread
  clears $\lambda$*. No quota, no foresight required, and the windows are
  independent for a fixed $\lambda$.

Valuing moves the difficulty into finding one number. That is what the dual is
for.

## 2. The Lagrangian

Write the dispatch problem as

$$
P^\star \;=\; \max_{x \in \mathcal{X}} \; f(x) \qquad \text{s.t.} \qquad n(x) \leq \overline{L}
$$

where $f(x) = \sum_{t} R(t)$ is the profit of §3, $n(x) = n_{\text{cyc}}(T)$ the
cycles the plan spends, and $\mathcal{X}$ the set of plans satisfying all
of §4 *except* the budget: the energy balance, the rate limits, the
charge/discharge binary, the hourly commitment of Market 2, the degradation.
$\mathcal{X}$ is therefore a mixed-integer set, and it is non-empty — doing
nothing is in it.

Attach a multiplier $\lambda \geq 0$ to the budget and move it into the
objective:

$$
\phi(x, \lambda) \;=\; f(x) \;-\; \lambda\,\bigl(n(x) - \overline{L}\bigr),
\qquad
L(\lambda) \;=\; \max_{x \in \mathcal{X}} \; \phi(x, \lambda)
$$

$L$ is the **dual function**, and evaluating it once means solving one relaxed
problem. The sign convention matters: for a $\leq$ constraint in a maximisation,
$\lambda \geq 0$ makes violation ($n(x) > \overline{L}$) expensive and slack
($n(x) < \overline{L}$) a bonus. The bonus is a constant $\lambda \overline{L}$
and so does not distort the plan; only the $-\lambda n(x)$ term does.

The separability that the decomposition needs is visible here. $n(x)$ is a sum
over periods of what each period discharges, so

$$
\phi(x, \lambda) \;=\; \lambda \overline{L} \;+\; \sum_{k} \Bigl[ \sum_{t \in \mathcal{W}_k} R(t) \;-\; \lambda \, \bigl(n_{\text{cyc}}(\text{end of } \mathcal{W}_k) - n_{\text{cyc}}(\text{start of } \mathcal{W}_k)\bigr) \Bigr]
$$

and each bracket involves only its own window's variables. A global row has
become a per-window charge. (The windows are still chained through $S$ and
through the cumulative count, which is why the implementation walks them in order
rather than solving them in parallel; what valuing buys is that no window needs
to know the *future*.)

## 3. Weak duality

For every $\lambda \geq 0$,

$$
L(\lambda) \;\geq\; P^\star
$$

*Proof.* Let $x^\star$ be optimal for the constrained problem. Then
$x^\star \in \mathcal{X}$ and $n(x^\star) \leq \overline{L}$, so
$-\lambda(n(x^\star) - \overline{L}) \geq 0$ and

$$
L(\lambda) \;\geq\; \phi(x^\star, \lambda) \;=\; f(x^\star) - \lambda\bigl(n(x^\star) - \overline{L}\bigr) \;\geq\; f(x^\star) \;=\; P^\star
$$

Two things are used: that the relaxed feasible set *contains* the constrained one
(relaxation never removes a plan), and the sign of $\lambda$. $\square$

So every evaluation of the dual is a certificate: no plan, however clever,
earns more than $L(\lambda)$. The tightest certificate this relaxation offers is

$$
D^\star \;=\; \min_{\lambda \geq 0} L(\lambda) \;\geq\; P^\star
$$

and finding it is the point of §5 below. The gap $D^\star - P^\star$ is the
**duality gap**. For a linear program it is zero; for a mixed-integer program it
generally is not, and §6 says why.

## 4. The shape of $L$, and its subgradient

### 4.1 Convex and piecewise linear

Hold $x$ fixed. Then $\phi(x, \cdot)$ is an **affine** function of $\lambda$,
with intercept $f(x)$ and slope $\overline{L} - n(x)$. $L$ is the pointwise
maximum of one such line per plan, and a pointwise maximum of affine
functions is convex. If $\mathcal{X}$ has finitely many extreme candidates — true
here, the binaries being finite and each fixing of them leaving an LP whose
optimum is attained at a vertex — the maximum is over finitely many lines, so $L$
is piecewise linear with finitely many kinks.

Note what this does *not* require: no convexity of $\mathcal{X}$, no continuity
in $x$, nothing about the integers. The dual of an integer program is convex in
the multiplier regardless. That is the whole appeal — an awkward primal has a
well-behaved dual in one variable.

Note also that $L$ is convex although the primal is a *maximisation*. Minimising
a convex function is the easy direction, which is why the dual is approached from
above by minimisation.

### 4.2 $\overline{L} - n(x_0)$ is an exact subgradient

This is property 2 of §6, and it follows from the same picture in one step.

Let $\lambda_0 \geq 0$, let $x_0 \in \arg\max_{x} \phi(x, \lambda_0)$ be a
maximiser of the relaxed problem at $\lambda_0$, and set

$$
g_0 \;=\; \overline{L} - n(x_0)
$$

Claim: $g_0 \in \partial L(\lambda_0)$, i.e. $L(\lambda) \geq L(\lambda_0) + g_0(\lambda - \lambda_0)$ for all $\lambda$.

*Proof.* The feasible set $\mathcal{X}$ does not depend on $\lambda$. So $x_0$
stays feasible at any other $\lambda$ — merely no longer necessarily optimal —
and the definition of $L$ as a maximum gives

$$
\begin{aligned}
L(\lambda) \;&\geq\; \phi(x_0, \lambda) \\[4pt]
           &=\; f(x_0) - \lambda\bigl(n(x_0) - \overline{L}\bigr) \\[4pt]
           &=\; \underbrace{f(x_0) - \lambda_0\bigl(n(x_0) - \overline{L}\bigr)}_{= \; L(\lambda_0)} \;+\; \bigl(\overline{L} - n(x_0)\bigr)(\lambda - \lambda_0) \\[4pt]
           &=\; L(\lambda_0) + g_0\,(\lambda - \lambda_0)
\end{aligned}
$$

which is the subgradient inequality. $\square$

The second line is the whole argument: $\phi(x_0, \cdot)$ *is* the line of slope
$g_0$ through $(\lambda_0, L(\lambda_0))$, and $L$ lies above every such line by
construction. The subgradient is not estimated, differenced, or inferred from two
evaluations — it is read off the solution the solver already returned. One solve
yields a value *and* a slope, at no extra cost. That is what makes the
cutting-plane method cheap relative to any method that only learns a value.

**What "exact" is asserting.** Two distinct things, both worth keeping straight:

- *Exact, not approximate.* The inequality needs $x_0$ to be a **true** maximiser
  of the relaxed problem. If the oracle returns an $x$ with
  $\phi(x, \lambda_0) \geq L(\lambda_0) - \varepsilon$, the same algebra gives
  only an $\varepsilon$-subgradient,
  $L(\lambda) \geq L(\lambda_0) - \varepsilon + g(\lambda - \lambda_0)$. The
  resulting cut can sit up to $\varepsilon$ *above* $L$ and so slice off the true
  minimiser, and the master's value stops being a valid lower bound. Two things
  in this implementation break exactness: a MILP stopped on a MIP gap rather than
  proved optimal, and a rolling pass with finite lookahead, which maximises
  window by window rather than over $\mathcal{X}$ as a whole. Both make the
  bracket of §5 approximate, and §6 of `model.md` says so.
- *A subgradient, not a gradient.* At a kink several plans tie as maximisers,
  and $\partial L(\lambda_0)$ is the interval between the smallest and largest of
  their slopes. The solver hands back one arbitrary element of it. Any element
  gives a valid cut, so the method is correct either way, but the iterates can
  oscillate across the kink, which is the motivation for stabilisation.

**Reading the sign.** $g_0 = \overline{L} - n(x_0)$ is the **unused budget** at
the current price.

| Sign | Meaning | What $\lambda$ should do |
| --- | --- | --- |
| $g_0 > 0$ | cycles left over; the price is too high and is suppressing profitable trades | decrease |
| $g_0 < 0$ | the relaxed plan overspends; cycles are undervalued | increase |
| $g_0 = 0$ | the plan spends exactly the budget | $\lambda$ is optimal |

Since $L$ is convex and $g_0$ is its slope, "decrease $\lambda$ when $g_0 > 0$"
is just descent. And $0 \in \partial L(\lambda^\star)$ at an interior minimum is
complementary slackness in disguise: at the optimal price, the budget is spent
exactly, which is what makes $\lambda^\star$ the budget's shadow price — the
marginal profit of one more cycle. $\lambda^\star = 0$ with $g_0 > 0$ is the
boundary case: the cap is not binding, and no price is needed. That is the
outcome on this data with the full 5,000-cycle budget.

## 5. Kelley's cutting-plane method

(Spelled *Kelley* — J. E. Kelley Jr., 1960. Not Helly, whose theorem concerns
intersections of convex sets; the two come up in neighbouring literature and the
names are easy to swap.)

The method exploits exactly what §4 provides and nothing more: at each queried
point, a value and a valid lower-bounding line. Having evaluated at
$\lambda_1, \dots, \lambda_k$ and collected $(L(\lambda_i), g_i)$, the **cut**

$$
\ell_i(\lambda) \;=\; L(\lambda_i) + g_i\,(\lambda - \lambda_i)
$$

lies everywhere below $L$ and touches it at $\lambda_i$. Their upper envelope
$\max_i \ell_i$ is therefore a piecewise-linear **model** of $L$ from below, and
it improves monotonically as cuts accumulate. The next query point is the
model's minimiser, a two-variable LP with one row per cut:

$$
\begin{aligned}
\min_{\lambda,\ \theta} \quad & \theta \\
\text{s.t.} \quad & \theta \geq L(\lambda_i) + g_i(\lambda - \lambda_i), \qquad i = 1, \dots, k \\
& 0 \leq \lambda \leq \lambda_{\max}
\end{aligned}
$$

This **master problem** is free beside one pass over the horizon. The box is not
cosmetic: with a single cut the envelope is an unbounded line, so some bound is
needed to make the first master solvable. $\lambda_{\max}$ should exceed any
plausible per-cycle value — the largest spread in the data times the storage
volume is a safe choice — since a binding $\lambda_{\max}$ at exit means the box,
not the dual, determined the answer.

### 5.1 The bracket

The method brackets $D^\star$ from both sides, which is its practical virtue:

$$
\theta^\star_k \;\leq\; D^\star \;\leq\; \min_{i \leq k} L(\lambda_i)
$$

The left inequality holds because the cuts underestimate $L$, so minimising the
model cannot overshoot minimising $L$. The right holds because each $L(\lambda_i)$
is an actual value of $L$ at a feasible $\lambda$, so the best one seen is an
upper bound on the minimum — and by weak duality on $P^\star$ as well.

The loop therefore terminates on a **measured** quantity,

$$
\min_{i \leq k} L(\lambda_i) \;-\; \theta^\star_k \;\leq\; \text{tol}
$$

rather than on an iteration count. The number at exit is a statement about the
quality of the answer, not a hope about it. Both bounds tighten monotonically:
each new cut can only raise the envelope, and each new evaluation can only
improve the best value seen.

### 5.2 Why this and not a one-dimensional search

The dual here is one-dimensional, so bisection on the sign of $g$ — or on the
feasibility bit of a capped pass — also works, and `model.md` reports both. Three
reasons to prefer cutting planes:

- **It uses more of each solve.** Bisection reads one bit per pass; the
  cutting-plane method reads a value and a slope. Fewer passes to the same
  tolerance, and a pass is a full sweep of the horizon.
- **It returns a bound.** Bisection converges on a price and says nothing about
  $P^\star$. The bracket above is a by-product here.
- **It generalises to a vector $\lambda$.** This is the structural reason. A
  time-varying allowance $\overline{L}(y)$ — a per-year quota, say — attaches one
  multiplier per quota period, with
  $g_y = \overline{L}_y - (\text{cycles spent in period } y)$. The subgradient
  argument of §4.2 goes through verbatim with an inner product in place of the
  product, the master simply widens to $Y + 1$ columns, and nothing else changes.
  A line search cannot represent that problem at all.

### 5.3 Where it is weak

- **Instability.** Kelley's iterates can jump to the far side of the box when the
  model is poor there, since the model is minimised globally with no regard for
  where the information was gathered. The classical remedies add a proximal term
  ($+\tfrac{1}{2\tau}\lVert \lambda - \hat\lambda \rVert^2$, giving a bundle
  method) or a trust region around the best point so far. A scalar $\lambda$ on
  these instances did not need it; a vector one would likely want a bundle.
- **Cut accumulation.** One row per pass, unbounded in principle. Irrelevant at
  the iteration counts here; cut pruning is the standard fix.
- **Tail convergence.** Kelley's method converges, but its rate near the optimum
  is poor compared with Newton-like methods — which are unavailable, $L$ being
  nondifferentiable at precisely the interesting point.

## 6. The duality gap, and primal recovery

Two loose ends, both consequences of the primal being a MILP.

**The gap does not close.** For a linear program, $D^\star = P^\star$. For a
mixed-integer program, $D^\star$ equals the optimum of the problem over the
*convex hull* of $\mathcal{X}$ intersected with the budget, which may exceed
$P^\star$ strictly. So $\min_\lambda L(\lambda)$ can be a loose upper bound and
no amount of dual iteration tightens it: the bracket of §5.1 closes around
$D^\star$, not around $P^\star$. The method remains correct — it returns a valid
bound and a valid plan — but "the dual converged" is not "the primal is
optimal".

**A dual solution is not a plan.** The plan $x_0$ returned by a relaxed
pass can overspend the budget: that is what $g_0 < 0$ reports, and an infeasible
plan is not an answer. The dual produces a *price*, not a plan. So the last
step is one final pass **with** the cap reinstated, charged at the $\lambda^\star$
the dual settled on. Its profit is a lower bound on $P^\star$ — it is an
achievable plan — and together with $\min_i L(\lambda_i)$ from above it
frames the answer. This is why §4.6 of `model.md` insists the budget be a *row*
rather than a variable bound: a row can be removed from the subproblem and
reinstated for the final pass, whereas a bound removes nothing and cannot be
valued.

## 7. Probability space, filtration, and non-anticipativity

Background for [`model-stochastic.md`](model-stochastic.md) §2.1, which states
the probability space and the filtration in four lines and then uses them. The
four lines carry more than they look like, and the rest of that document — the
tree, the node copies of every variable, the measurability rows of its §5.6 — is
machinery for representing them. This section unpacks what each object is for,
and ends at the one place where it meets §2 above.

### 7.1 The three objects

$(\Omega, \mathcal{F}, \mathbb{P})$ is the standard triple, and each part answers
a different question.

- $\Omega$, the **sample space**, is the set of possible futures. A point
  $\omega \in \Omega$ is one complete realisation: a value for $p_1(t)$ and
  $p_2(t)$ at every $t \in \mathcal{T}$, the whole three years at once. Not a
  price, not a path-so-far — an entire history. Choosing $\omega$ is choosing
  which world happened.
- $\mathcal{F}$, a **$\sigma$-algebra** on $\Omega$, is the collection of subsets
  to which a probability can be attached. Its members are called events, and the
  closure properties required of it — under complement and countable union — are
  what make "not $A$", "$A$ or $B$" and "$A$ and $B$" events whenever $A$ and $B$
  are. An event is a *question about the future answerable yes or no*: "the
  Market 1 price exceeds £200 at some point in June 2019" is a subset of
  $\Omega$, namely the set of worlds in which that holds.
- $\mathbb{P}$ assigns each event a number in $[0,1]$, countably additively, with
  $\mathbb{P}(\Omega) = 1$.

The price process is then a function of two arguments, $p_m(t, \omega)$, and two
readings of it are worth keeping apart. Fix $\omega$ and vary $t$: one price
path, a column of a spreadsheet, which is what `model.md` optimises against.
Fix $t$ and vary $\omega$: a **random variable**, the price at that period
viewed before it is known. The deterministic model does the first; the stochastic
model has to do both at once, and the apparatus below exists for that.

For a finite tree all of this is modest: $\Omega$ is the leaf set $\mathcal{L}$,
$\mathcal{F}$ is its power set, and $\mathbb{P}$ is the leaf probabilities
$\pi(\omega)$. The measure-theoretic vocabulary is not needed to *state* the
finite model — it is needed to say what the finite model approximates, and to say
precisely what a decision is allowed to depend on.

### 7.2 The filtration: what is known, and when

A probability space says what might happen. It does not say *when* one finds out.
That is the filtration's job:

$$
\mathcal{F}_0 \subseteq \mathcal{F}_1 \subseteq \dots \subseteq \mathcal{F}_K = \mathcal{F}
$$

Each $\mathcal{F}_k$ is itself a $\sigma$-algebra on $\Omega$, and it is the
collection of events **decidable by stage $k$** — questions an observer standing
at stage $k$, having watched prices settle, can already answer. Three features
of the definition, each doing work:

- **Nested.** $\mathcal{F}_k \subseteq \mathcal{F}_{k+1}$ says information is
  never lost: what was decidable yesterday is decidable today. This is the formal
  content of "observing prices as they settle".
- **$\mathcal{F}_0$ trivial**, i.e. $\{\emptyset, \Omega\}$. At the root nothing
  is known beyond the distribution itself: the only questions answerable are the
  ones whose answer is the same in every world. This is why the root decision is
  a single vector rather than a family — there is nothing for it to vary with.
- **$\mathcal{F}_K = \mathcal{F}$.** By the end of the horizon everything is
  known. The last stage of a stochastic program is a deterministic problem, which
  is why §9 of `model-stochastic.md` can compare against per-scenario
  deterministic solves at all.

A filtration is therefore a plan of revelation laid over a fixed set of
possible futures. The futures do not change as time passes; what changes is how
finely one can distinguish them.

### 7.3 Measurability, and why it is the same thing as the tree

"A decision at stage $k$ must be $\mathcal{F}_k$-measurable" is the one
structural addition to the deterministic model. For a finite space, measurability
has a wholly concrete reading, and it is worth doing the translation explicitly
because it is what licenses the node indexing.

A $\sigma$-algebra on a finite $\Omega$ is generated by a **partition** of
$\Omega$: its minimal non-empty members, the *atoms*. The atoms of
$\mathcal{F}_k$ partition the set of futures into bundles that stage $k$ cannot
tell apart. A function $x : \Omega \to \mathbb{R}$ is $\mathcal{F}_k$-measurable
exactly when it is **constant on each atom**. The chain of inclusions in §7.2
says the partitions refine as $k$ grows: each atom of $\mathcal{F}_k$ splits into
one or more atoms of $\mathcal{F}_{k+1}$ and never merges.

That refining sequence of partitions *is* a tree. One identification, written out:

| Measure-theoretic object | Tree object in §2.2 |
| --- | --- |
| $\omega \in \Omega$ | a leaf $\omega \in \mathcal{L}$, i.e. one scenario |
| an atom of $\mathcal{F}_k$ | a node $n \in \mathcal{N}_k$ |
| $\mathcal{F}_0$ trivial — one atom | the root $r$ |
| atoms refine as $k$ grows | a node's children partition its scenarios |
| $\mathcal{F}_K = \mathcal{F}$ — atoms are singletons | the leaves, one per scenario |
| $\mathbb{P}(\text{atom})$ | $\pi(n)$ |
| $x$ is $\mathcal{F}_k$-measurable | $x$ has one value per node at stage $k$ |

The last row is the payoff. **Indexing a decision variable by node *is*
non-anticipativity** — not an approximation of it, a representation of it. A
variable written $c_1(n, \tau)$ cannot distinguish two scenarios that share $n$,
because there is only one variable for both. That is why
`model-stochastic.md` §5.6 says the measurability constraint is *vacuous* when
$\ell_m = 0$: the indexing already enforces it, and a row would be redundant.
Rows are needed only when a decision must be measurable with respect to a
*coarser* $\sigma$-algebra than its own node's — $\mathcal{F}_{k - \ell_m}$ for a
volume committed $\ell_m$ stages ahead — and then the row equates siblings that
the node indexing would otherwise let differ.

The scenario form of that document's §8 makes the same point from the other side.
There every scenario gets a full-horizon copy, so a variable *can* distinguish
scenarios that stage $k$ cannot, and measurability must be imposed as explicit
rows — the split-variable constraints. Node form builds non-anticipativity into
the index set; scenario form states it as constraints. Same feasible set, and
the choice between them is which structure a solution method wants to exploit.

The reason $\pi(n) > 0$ is required, incidentally, is this correspondence: a node
of probability zero is an atom that cannot occur, and it would add decision
variables that the objective never weighs — unconstrained in effect, and free to
take any value in a reported solution.

### 7.4 The one adapted process worth naming

$S$ and $n_{\text{cyc}}$ are not decisions, but they inherit measurability from
the decisions that produce them: each is a function of the discharge and charge
along the path to its node, so each is automatically $\mathcal{F}_k$-measurable
at stage $k$. Such a process is **adapted** to the filtration. This is the formal
statement of what §5.3 of `model-stochastic.md` asserts physically — that every
child of a node opens from the same state. The state is a consequence of
decisions already taken and prices already seen, so it cannot depend on which
child is about to be drawn. A state that *did* differ across siblings would be
a policy peeking at the next price.

Conditional expectation is the operation that moves between levels of the
filtration: $\mathbb{E}[\,\cdot \mid \mathcal{F}_k]$ averages out everything not
yet decidable at stage $k$, and on a tree it is the weighted sum over a node's
descendants. The tower property,
$\mathbb{E}\bigl[\mathbb{E}[X \mid \mathcal{F}_{k+1}] \mid \mathcal{F}_k\bigr] =
\mathbb{E}[X \mid \mathcal{F}_k]$, is what collapses the nested expectation of a
multistage objective into the single probability-weighted sum of
`model-stochastic.md` §4. Without it the objective would have to be written
stage by stage; with it, the deterministic equivalent is one linear objective
over all node copies at once.

### 7.5 Where this meets the Lagrangian

Two connections to §2–§6 above, both of which the stochastic note states in
passing.

**The cycle budget acquires a domain.** M§4.6's cap is one row, so §2's
multiplier is one number. Under uncertainty the cap is a statement about paths,
and which paths it quantifies over decides the dual's dimension: reading (a) —
almost surely — is one row per scenario and so one multiplier per scenario;
reading (b) — in expectation — is one row for the tree and one multiplier,
exactly as in the deterministic case. The subgradient argument of §4.2 is
unchanged in either, with $g$ becoming a vector whose component for a scenario is
that scenario's unused budget, and with the master program of §5 widening to one
column per multiplier. This is the vector case that §5.2 gives as the structural
argument for cutting planes over a line search; here it arises from the
uncertainty rather than from a per-year quota, but the algebra is identical.

**Non-anticipativity is itself relaxable, and that is a different algorithm.**
The split-variable rows of the scenario form couple scenarios and nothing else.
Relax *them* with multipliers and the problem separates into one deterministic
program per scenario — each exactly the program of `model.md` — coordinated by a
price on disagreement. That is progressive hedging, and it is the same
Lagrangian idea applied to a different coupling constraint: §2 above prices a
physical budget, this prices the requirement that a policy not look ahead. The
MILP caveat of §6 applies with equal force, the recourse binaries
$u(n, \tau)$ being precisely what makes the value function non-convex and the
duality gap real.

---

## 8. Building the tree: nodes, branching, and size

Background for [`model-stochastic.md`](model-stochastic.md) §6, which states the
deterministic equivalent's size in four formulas and one table, and §10, which
defers tree construction entirely. The deferral is correct — how a tree is built
is prior to the formulation and independent of it — but it leaves the reader of
§6 with the formulas and not the reason the numbers in them are what they are.
This section derives the counts, says what a node has to carry and how to
assemble one, and then asks which dimension of the tree is actually expensive.
Throughout, **MS§6** means §6 of `model-stochastic.md`, as **M§4.6** means §4.6
of `model.md`.
The answer is not the one §6's table suggests.

### 8.1 What a node is, and what it is not

Three things are attached to a node, and keeping them apart is most of the
construction:

| On a node | What it is | Who supplies it |
| --- | --- | --- |
| $p_1(n,\tau),\ p_2(n,\tau)$, $\tau = 1 \dots 48$ | **data** — one realised price vector per market | the tree builder |
| $\pi(n)$ | **data** — the unconditional probability of reaching $n$ | the tree builder |
| $c_1, c_2, d_1, d_2, S, u, n_{\text{cyc}}$ | **variables** — one copy per node | the solver |

The split is what keeps the program linear (MS§2.2) and it is also the division
of labour: the tree builder never sees a decision, and the solver never sees a
distribution. A node is not a state of the battery and not a point in time. It is
an *atom of $\mathcal{F}_k$* — §7.3's identification — i.e. a bundle of futures
that are indistinguishable on the day it stands for. Everything in this section
follows from reading it that way.

Two asymmetries of MS§2.3 are easy to lose and both matter for the counts
below:

- **The root carries variables but no prices.** Day 0 is committed under the
  prior, so $r$ holds a plan and no data.
- **The leaves carry prices but no variables.** Their day was committed at their
  parent, so a leaf contributes data to its parent's conditional mean
  $\bar p_m(a(\omega), \tau)$ and nothing else.

So the tree has $K+1$ levels of nodes but only $K$ levels of *decisions*, and the
last level of branching buys scenarios for free. §8.5 is largely that observation.

### 8.2 The branching rule has to get exactly two things right

The branching rule is the map from a node to its children: how many, with what
probabilities, carrying what prices. MS§4.2 and MS§7 together pin down what it
must deliver, and it is less than one might fear and more than one might hope.

**What the objective demands: conditional first moments.** By MS§4.2 the prices
enter the program only through
$\bar p_m(n,\tau) = \sum_{m' \in \mathcal{C}(n)} \tfrac{\pi(m')}{\pi(n)} p_m(m',\tau)$.
A branching rule is therefore free to distribute a node's children however it
likes, provided their probability-weighted mean is right: two rules with the same
conditional means give **the same objective**, period by period and market by
market. This is a weak demand, and MS§8 warns against reading it as a licence.

**What the constraints demand: history dependence.** The reason is MS§7's second
check. If $\bar p_m(n, \cdot)$ depends only on the day and not on which node of
that day, every node of a day holds the same data, an optimal solution exists
that is the same at all of them, and $\mathrm{VSS} = 0$: the tree has cost
geometric growth and bought nothing. So the rule's real job is to make *tomorrow's
conditional mean move with what was seen today*. A rule that samples each day's
prices independently of history — resampling a marginal, say — satisfies the first
demand exactly and the second not at all, and produces a tree whose optimum is the
deterministic optimum on the mean path. That failure is silent: the program solves,
the policy differs across nodes only through the state, and nothing reports it.

A third demand is implicit and belongs to the constraints too: the *within-day
shape* of the price vector. The dispatch profit of a day is driven by the
intraday spread, not the daily level — a day whose 48 prices are all £60 earns
nothing however likely it is. Since a node's data is a point in $\mathbb{R}^{96}$,
matching all of its moments is hopeless and matching the wrong ones is cheap. The
functionals worth matching are the ones the dispatch actually integrates against:
the conditional distribution of the daily spread statistic (the mean of the top
$h$ periods less the mean of the bottom $h$, for $h$ near the storage's
duration), and the $p_1$–$p_2$ level gap, which is what makes the two-market
arbitrage worth anything. This is a heuristic argument rather than a theorem, but
it is the right shape of one: match the scalar the objective is nearly a function
of, and inherit the rest of the profile from the fitted process.

### 8.3 A construction

Nothing below is specific to a branching rule; it is the bookkeeping that any
rule needs, and it is worth writing out because the state handover of MS§5.3
makes the node ordering load-bearing.

```
fit         a conditional model  P[ day-k price vector | history ]   (not part of M-S)

build(n, k):                         # n a node at day k-1, k < K
    if k == K:  return               # leaves: no children to draw
    draw  b_k  children of n  from the conditional model at n's history
    assign each child m:  p_1(m,·), p_2(m,·)  and  q(m | n)  with  sum q = 1
                          pi(m) = pi(n) * q(m | n)
    for each child m:  build(m, k + 1)

build(r, 0)                          # pi(r) = 1

then, in the same depth-first order:
    for each n in D:                 # D = nodes with children
        pbar_m(n, tau) = sum over children m' of  (pi(m')/pi(n)) * p_m(m', tau)
        emit columns   c1,c2,d1,d2,S,u,ncyc   for tau = 1..48
        emit rows      M-S 5.1, 5.2, 5.4, 5.5, 5.6, 5.7
        bind           S(n,0), ncyc(n,0)  to  a(n)'s period-48 columns   (5.3)
```

Three details the pseudocode is making a point of:

- **$\pi$ is built multiplicatively, down the path.** The tree builder supplies
  *conditional* branch probabilities $q(m \mid n)$; MS§2.2's $\pi(n)$ is their
  product along $\text{path}(n)$. The consistency condition
  $\pi(n) = \sum_{m \in \mathcal{C}(n)} \pi(m)$ is then automatic rather than
  something to check, and $\sum_{n \in \mathcal{N}_k} \pi(n) = 1$ follows by
  induction. Requiring $\pi(n) > 0$ (§7.3) means requiring every $q(m \mid n) > 0$,
  which a sampler gives for free and a reduction algorithm can destroy.
- **Depth-first emission puts every parent before its children.** The handover is
  the only inter-node coupling, and it reaches backwards only. In a DFS numbering
  $a(n) < n$, so the whole program is assembled in one forward pass with no
  second pass to patch the day boundaries, and the constraint matrix is lower
  block-triangular in the node index — the structure any decomposition would want
  and the reason a nested-Benders scheme is the natural thing to reach for if the
  integers of MS§10 were not in the way.
- **A node's data is consumed by its parent, not by itself.** $\bar p_m(n,\cdot)$
  is computed from $\mathcal{C}(n)$, so the children must exist before $n$'s
  objective coefficients can be written. Build the whole tree first, then emit.
  This is the one ordering constraint that pulls the other way from the DFS, and
  it is why the pseudocode has two phases rather than one.

The deterministic model is the $b_k \equiv 1$ case of exactly this loop, which is
MS§7's first check: one child per node, $\bar p_m(n,\cdot)$ the next day's
actual price, and the recursion degenerates to a walk along a single path. A
correct implementation should reduce to the one in `model.md` by setting a
parameter, not by taking a different code path.

### 8.4 Where the size comes from

MS§6's four formulas are one geometric series, and deriving them makes the next
subsection's argument visible. With uniform branching $b$, the root has $b$
children, so

$$
|\mathcal{N}_k| \;=\; b^{\,k+1}, \qquad k = 0, \dots, K-1
$$

and therefore

$$
|\mathcal{N}| \;=\; 1 + \sum_{k=0}^{K-1} b^{\,k+1} \;=\; \sum_{j=0}^{K} b^{\,j} \;=\; \frac{b^{K+1}-1}{b-1},
\qquad
|\mathcal{L}| \;=\; |\mathcal{N}_{K-1}| \;=\; b^{K}
$$

The decision nodes are everything but the leaves, which removes the last and
largest term of the series:

$$
|\mathcal{D}| \;=\; |\mathcal{N}| - |\mathcal{L}| \;=\; \sum_{j=0}^{K-1} b^{\,j} \;=\; \frac{b^{K}-1}{b-1}
$$

so $|\mathcal{D}|$ is the same series one level short — $|\mathcal{D}| \approx
|\mathcal{N}| / b$, and almost all of a tree's *nodes* are leaves while none of
its *variables* are.

The per-node cost is measured rather than assumed.
[`tractability.md`](tractability.md) reports the three-year deterministic program
at 368,256 columns and 315,649 rows over 52,608 periods, i.e. **7.0 columns and
6.0 rows per period** after the substitutions of M§4.7, and MS§5 is M§4 verbatim
within a node. A decision node is 48 periods, so

$$
\text{columns} \approx 336\,|\mathcal{D}|, \qquad
\text{rows} \approx 288\,|\mathcal{D}|, \qquad
\text{binaries} = 48\,|\mathcal{D}|
$$

the last being MS§6's figure exactly. The one-week $b = 3$ tree is then $1{,}093$
decision nodes, $\approx 0.37$M columns and $52{,}464$ binaries, which is MS§6's
comparison: a **week** of three-way branching is the three-year deterministic
program, whose hour-long run stopped at a 2.02% gap.

### 8.5 Which dimension is expensive

$|\mathcal{D}| = (b^K - 1)/(b-1)$ is geometric in $K$ and polynomial of degree
$K-1$ in $b$, so the two enter quite differently: a day costs a factor of $b$,
a branch costs a factor of $((b{+}1)/b)^{K-1}$. Tabulated:

| $|\mathcal{D}|$ | $b=2$ | $b=3$ | $b=5$ |
| --: | --: | --: | --: |
| $K=3$ | 7 | 13 | 31 |
| $K=5$ | 31 | 121 | 781 |
| $K=7$ | 127 | 1,093 | 19,531 |
| $K=10$ | 1,023 | 29,524 | 2,441,406 |
| $K=14$ | 16,383 | 2,391,484 | 1,525,878,906 |

Now the sobering part, and the reason the comparison in MS§6 is generous rather
than harsh. The binary count of the three-year deterministic program is the wrong
yardstick, because that program *was not solved* — it stopped at 2.02%. The
yardstick for a **provable** solve is the cliff in `tractability.md`: a 30-day
window (1,440 binaries) proved optimal in 30 s, and a 60-day window (2,880
binaries) could not be proved in 900 s. Taking $\approx$ 2,000 binaries as the
envelope, i.e. $|\mathcal{D}| \lesssim 40$:

| $b$ | largest $K$ with $|\mathcal{D}| \lesssim 40$ | scenarios |
| --: | --: | --: |
| 2 | 5 | 32 |
| 3 | 4 | 81 |
| 5 | 3 | 125 |

A **five-day tree with two-way branching**. That is the honest size of what a
direct solve reaches, and it is two orders of magnitude short of the week-long
$b=3$ tree that MS§6 already calls out as infeasible. Two caveats pulling in
opposite directions, neither large enough to change the conclusion: a tree MILP
is *easier* per binary than a long deterministic one in that its coupling is only
two state variables deep per node rather than a 52,608-period chain; and *harder*
in that sibling subtrees are near-identical, and branch-and-bound explores
symmetric subproblems redundantly unless told not to. The second is the one to
worry about — symmetry is the classic way a structured MILP underperforms its
size.

**The cost of a branch falls with its stage, and the last one is free.** This is
the structural fact worth carrying away, and it is clearest with non-uniform
branching $b_0, \dots, b_{K-1}$, where $|\mathcal{N}_k| = \prod_{j=0}^{k} b_j$ and

$$
|\mathcal{D}| \;=\; 1 + \sum_{k=0}^{K-2} \; \prod_{j=0}^{k} b_j,
\qquad
|\mathcal{L}| \;=\; \prod_{j=0}^{K-1} b_j
$$

Read off which $b_j$ appears where. $b_0$ multiplies every one of the $K-1$ terms;
$b_{K-2}$ multiplies only the last; and $b_{K-1}$ appears in $|\mathcal{L}|$ and
**not in $|\mathcal{D}|$ at all**. So the final level of branching adds scenarios,
sharpens the last decision nodes' conditional means, and adds not one column to
the program. The leaves carry no decisions (§8.1), and this is what that
asymmetry is worth.

This cuts against the usual instinct to branch widest at the root. The instinct is
not wrong about where the *information* matters — in a rolling scheme only the
root's commitment is ever implemented, and everything beyond it exists to value
that commitment correctly. But the root decision is a single vector no matter what
$b_0$ is; what $b_0$ buys is the number of distinct day-1 plans, and past two or
three that is refinement of an estimate at a cost multiplying the entire tree. The
defensible shape is therefore modest branching early, $b_j = 1$ through the middle
(stage aggregation: later days represented by a deterministic continuation), and a
wide free level at the end. For instance $b = (3, 2, 1, 1, 12)$ over $K = 5$ gives
$|\mathcal{D}| = 1 + 3 + 6 + 6 + 6 = 22$ decision nodes — 1,056 binaries, inside
the provable envelope — and $3 \cdot 2 \cdot 12 = 72$ scenarios. Uniform $b = 2$
at the same $K$ costs 31 nodes for 32 scenarios. Same order of program, twice the
scenarios, and the extra ones placed where they cost nothing.

### 8.6 Why a recombining lattice does not rescue this

The standard escape from geometric growth is to merge nodes: a binomial lattice
has $|\mathcal{N}_k| = k + 2$ rather than $b^{k+1}$, turning the size from
geometric in $K$ to quadratic, and three years becomes $\approx 600{,}000$ nodes —
large but finite, where $2^{1096}$ is not. It does not work here, and the reason
is a property of this model rather than of lattices.

Merging two nodes asserts that the future seen from them is identical, which
requires that they agree on the whole state, not just on the price. The state is
$(S, n_{\text{cyc}})$ (MS§8), and $n_{\text{cyc}}$ is **path dependent** by
MS§5.6 — it is the throughput along $\text{path}(n)$ and nothing else — so two
nodes reached by different price histories have spent different numbers of cycles
and, by MS§5.7, hold batteries of different usable volume $S_{\max}$. The prices
may recombine; the battery does not. A node is an atom of $\mathcal{F}_k$ (§7.3),
and merging atoms that the decisions distinguish is not a coarsening of the
filtration but a misstatement of it.

The way to have both is to put the state back in the index — a value function
$V_k(S, n_{\text{cyc}}, \text{price state})$ on a recombining price lattice,
which is dynamic programming and whose node count is the lattice's, not the
tree's. That is exactly the door MS§10 closes: the $u(n,\tau)$ are integer, so
$V_k$ is not concave in the state, and the cutting-plane approximations (SDDP and
relatives) that make this tractable for linear recourse are not valid without
further work. The geometric growth of §8.4 and the non-convexity of MS§10 are
therefore not two separate obstacles but the same one seen twice: the
path-dependent, integer-driven state is what forbids both merging nodes and
approximating the value function.

### 8.7 Checks a tree should pass

Each is cheap, and each catches a failure that is otherwise silent.

| Check | Catches |
| --- | --- |
| $b_k \equiv 1$ reproduces `model.md`'s optimum (MS§7) | the emission loop of §8.3, the handover, the sign of the objective |
| $\sum_{n \in \mathcal{N}_k} \pi(n) = 1$ for every $k$; all $\pi(n) > 0$ | a reduction step that dropped mass or left a zero-probability atom |
| $\bar p_m(n,\cdot)$ varies across $n \in \mathcal{N}_k$ | the §8.2 failure: a history-independent rule, hence $\mathrm{VSS} = 0$ |
| $\mathrm{RP}$ stable across trees re-sampled at the same $b$ | in-sample instability — the answer is reading the sample, not the process |
| a policy from tree A evaluated on tree B, and vice versa | out-of-sample instability, which the previous check cannot see |
| $0 \leq \mathrm{VSS}$ and $0 \leq \mathrm{EVPI}$ (MS§7) | sign and weighting errors in the objective; both are theorems, so a violation is a bug |

The two stability checks are the ones that decide whether any reported number
means anything. MS§8 says every quantity computed from a tree is conditional on
it; these are how that conditionality is measured rather than merely conceded.
And since MS§10 makes VSS the quantity to establish first, note the order the
checks impose: a VSS computed on a tree that fails the third row is guaranteed to
be zero, and a VSS computed on a tree that fails the fourth is noise.

---

## 9. Summary

| Claim | Rests on | Fails when |
| --- | --- | --- |
| $L$ convex, piecewise linear | pointwise max of lines affine in $\lambda$ | never (independent of the primal's structure) |
| $g = \overline{L} - n(x_0)$ is a subgradient | $\mathcal{X}$ independent of $\lambda$; $x_0$ a true maximiser | the oracle is inexact — MIP gap, finite lookahead |
| $L(\lambda) \geq P^\star$ | relaxation enlarges the feasible set; $\lambda \geq 0$ | $\lambda < 0$; an inexact oracle |
| $\theta^\star_k \leq D^\star$ | cuts underestimate $L$ | an inexact oracle (cuts may rise above $L$) |
| $D^\star = P^\star$ | LP duality | the primal has integers — generally a gap |
| node indexing enforces non-anticipativity | atoms of $\mathcal{F}_k$ are the stage-$k$ nodes | a decision must be measurable w.r.t. a *coarser* $\sigma$-algebra — then rows are needed |
| the objective is one weighted sum | the tower property on the tree | nothing, given a finite tree with $\pi(n) > 0$ |
| $|\mathcal{D}| = (b^K-1)/(b-1)$, binaries $= 48|\mathcal{D}|$ | uniform branching; leaves carry no decisions | non-uniform $b_k$ — then it is $1 + \sum_k \prod_{j \leq k} b_j$ |
| the last level of branching is free | $b_{K-1}$ enters $|\mathcal{L}|$ but not $|\mathcal{D}|$ | same-day commitment, which puts decisions on the leaves |
| the conditional means are all the objective sees | linear revenue, node-deterministic volumes | the constraints still see the branching, and $\mathrm{VSS}$ lives there |
| merging nodes is invalid | $n_{\text{cyc}}$, hence $S_{\max}$, is path dependent | never, under this degradation model |

## Further reading

- Fisher, *The Lagrangian Relaxation Method for Solving Integer Programming
  Problems* (1981) — the standard account, including why integer duals gap.
- Lemaréchal, *Lagrangian Relaxation*, in *Computational Combinatorial
  Optimization* (2001) — subgradients, bundle stabilisation, and why Kelley alone
  oscillates.
- Kelley, *The Cutting-Plane Method for Solving Convex Programs*, SIAM J. (1960).
- Bertsekas, *Nonlinear Programming*, ch. 6 — subdifferentials of max functions
  and the Danskin theorem that §4.2 is a special case of.
- Shapiro, Dentcheva and Ruszczyński, *Lectures on Stochastic Programming*,
  ch. 1–3 — filtrations, non-anticipativity and the two forms of §7.3.
- Birge and Louveaux, *Introduction to Stochastic Programming*, ch. 2–4 — trees,
  the deterministic equivalent, EVPI and VSS.
- Rockafellar and Wets, *Scenarios and Policy Aggregation in Optimization under
  Uncertainty* (1991) — progressive hedging, i.e. §7.5's second connection.
- Høyland and Wallace, *Generating Scenario Trees for Multistage Decision
  Problems*, Management Science (2001) — moment matching, i.e. §8.2's first
  demand made into an algorithm.
- Kaut and Wallace, *Evaluation of Scenario-Generation Methods for Stochastic
  Programming* (2007) — the in-sample and out-of-sample stability tests of §8.7.
- Heitsch and Römisch, *Scenario Tree Modeling for Multistage Stochastic
  Programs*, Comput. Optim. Appl. (2009) — forward construction and reduction,
  with the filtration distance that justifies them.
- Pereira and Pinto, *Multi-stage Stochastic Optimization Applied to Energy
  Planning* (1991) — SDDP, i.e. what §8.6 would reach for if the binaries of
  `model-stochastic.md` §10 allowed it.
