# patches/

The working tree is **unpatched**. `scripts/apply-patches.sh` applies `NNNN-*.patch` in order at
build time (CI and `release.yml`); a rejected hunk fails the build. `scripts/revert-patches.sh`
restores the files listed in `paths.txt`. The pre-commit hook (`scripts/install-hooks.sh`) refuses
to commit a patched upstream file.

Each patch starts with a header block (ignored by `git apply`) recording: Title, Insertion point,
Upstream tag written against, Hunks, Added lines, FR reference, Owner approval date.

Regenerating a patch after an upstream move: apply the intent by hand in the working tree,
`git diff -- <file> > patches/NNNN-name.patch`, re-add the header, run `scripts/revert-patches.sh`,
then `scripts/apply-patches.sh --check`.
