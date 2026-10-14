# A Sequence is its own workflow, not a Panel of the grid

Slices 11 and 12 were agreed as Sequences inside the grid: several Sources sharing one Panel, one of them the Anchor carrying the Panel's Sync Point, the others placed outwards from it, with fades to black only because two Sources could never be on show in one Panel at once. In use the editor serves two separate jobs: clip after clip with transitions, where nothing is synced, and the same event from several views, where everything is. Putting the first inside the second made a plain run of clips pay for Sync Points, Lead-in, Lead-out and an Anchor it has no use for, and made the grid carry rules it rarely needs. We decided that a Project is either a Synced grid or a Sequence, chosen with a switch at the top of the page, and that a Sequence reaches a grid only as a rendered file added like any other Source.

## Considered Options

- **Sequences inside grid Panels, with an Anchor (the earlier agreement).** One Output can mix both, but every Sequence is placed on Event Time and every grid Panel can hold a play order, so each workflow carries the other's settings and rules.
- **Two separate pages, each with its own Projects.** Nothing can collide, but changing one's mind after adding Sources means adding them again, and the shared picture settings are built twice.
- **One app, one Project, a switch between two workflows (chosen).** Sources and their crop, rotation, resize and aspect are shared; each workflow's own settings are kept, unused, while the other is chosen.

## Consequences

- The Anchor is no longer a term. A grid Panel holds at most one Source, as after slice 10.
- Free of Event Time, a Sequence can crossfade, mix sound during a crossfade and give each Source its own Play Speed; its running time follows from its Sources rather than from a Lead-in and Lead-out.
- A Sequence shown in a grid is rendered first. A change to it means rendering it again; the grid Project does not follow it.
- The screen hides each workflow's settings in the other, and the Project file keeps both.
