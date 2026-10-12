# Panels are set up first and have typed sizes

Until slice 9 a Panel was not something the user made. Each Source had a Row, its order in the Row gave its Column, and the Sources set the sizes: the first Source set the height of the first Row, each Source in that Row set the width of its Column, and every Source after that was fitted with Bars. Sequences, where several Sources share one Panel, gave that model nowhere to keep what belongs to the Panel and not to any one Source. We decided that Panels are set up in a layout, each with a Row and a width and height typed by the user, and that Sources are then assigned to them. No Source sets the size of a Panel, and Panels in different Rows need not line up, so Column is no longer a term.

## Considered Options

- **The Anchor sets its Panel's size.** Every old rule would read the same with "the Panel's Anchor" in place of "the Source", and a row of Sources would still size itself. Rejected because it keeps sizes flowing from footage: cropping one Source resizes its Panel and every Panel that depends on it, and layouts such as one large Panel over three small ones cannot be made.
- **A strict grid typed per Row and per Column.** Fewer numbers and always tidy, but a Panel has no size of its own and the same layouts are impossible.
- **Typed size on each Panel, free Rows (chosen).** The layout is exactly what was typed and never moves when a Source is cropped, rotated, removed or reordered.

## Consequences

- A Source no longer fills its Panel by construction. Each Source has its own resize, is centred in its Panel, gets Bars where it is smaller and is cut off evenly where it is larger. "Scale width to Panel" and "Scale height to Panel" fill in that resize once; a later crop or Panel change leaves it as typed.
- A new Panel still starts at its Row's height and the width that fits its Source, so adding Sources side by side needs no typing. After that the size changes only when retyped.
- The Project file lists its Panels (format 3). An older Project is opened by giving each Source a Panel of the size the old rules gave it. The old sizing arithmetic is kept for that purpose only.
- A layout can leave black: an empty Panel, a Panel shorter than its Row, or a Row narrower than the Output. All of it is something the user typed and can see in the Preview.
