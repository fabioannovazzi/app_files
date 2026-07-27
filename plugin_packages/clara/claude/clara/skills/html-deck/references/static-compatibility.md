# Static-deck compatibility profile

Use this profile only for an externally constrained HTML deck that must retain
linked local CSS/JavaScript and a simple static stage. New Clara decks use the
default strict stage contract.

The compatibility profile still blocks remote dependencies, network APIs,
dynamic evaluation, missing or escaping local resources, unsafe markup, and
unsupported interaction patterns. Browser QA still requires an exact
1280×720 canvas, checks every slide for clipping, overflow, and collisions,
exercises Home/End/Arrow navigation, and captures every slide independently.

It intentionally does not require Clara-native notes, HUD, overview, content
ledger, content-addressed publication path, embedded resources, print package,
or standalone runtime. Those omissions are compatibility allowances, not a
general relaxation of the Clara authoring standard.

Run both gates:

```bash
python skills/html-deck/scripts/validate_html_deck.py \
  <linked-deck>/index.html \
  --profile static \
  --content-spec <controlling-spec>/deck_spec.json

python skills/html-deck/scripts/browser_qa_html_deck.py \
  <linked-deck>/index.html \
  --output-dir <output>/browser-qa \
  --profile static \
  --viewport benchmark=1280x720 \
  --warnings-as-errors
```

When the external contract includes a controlling JSON deck specification,
always pass it with `--content-spec`. The validator then compares each slide's
visible text token multiset with the specified text fields, KPI labels and
values, and page number. Missing, duplicated, or extra visible copy is an
error; this is a mechanical copy gate, not a semantic review.

If the deck can be migrated without violating its controlling specification,
return to the default strict Clara stage instead of extending this exception.
