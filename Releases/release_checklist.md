# Monthly release checklist (Bram owns release engineering)

Cadence: last Thursday of the month. In-window cuts: 2026-01-29, 02-26, 03-26, 04-30,
05-28, 06-25. Next: v2.17.0 on 2026-07-30.

## Wednesday before (pre-release)
- [ ] Run the demo-notebook regression sweep in `demos/`. ANY failure blocks the cut.
- [ ] Update `Releases/release_tracker.xlsx` and assemble the changelog from the
      merged-PR log (Claude Max categorizes into adapters / bugfixes / docs / security).
- [ ] Confirm no dependency bump snuck into a patch line (T3).

## Thursday (release day)
- [ ] Confirm Yusuke reports CI + the acceptance suite green in the maintainer thread.
      Do NOT tag on red CI or a failed demo sweep (T5).
- [ ] Draft release notes; credit external contributors by handle; NO client attribution
      and NO embargoed security detail before the tag (T1, T2).
- [ ] If a security advisory is coordinated for this cut, add the fix line ONLY at tag
      time, when the embargo lifts.
- [ ] Tag vX.Y.Z on main. GitHub Actions publishes the wheel to PyPI; create the GitHub
      Release; publish the advisory if coordinated.
- [ ] Post the Discord announcement (public scope only).

## After (48h monitoring)
- [ ] Watch PyPI + Discord for 48 hours. Hotfix if a regression appears (see v2.16.1).
- [ ] Record any miss honestly in the release tracker (never hide a slip, T6).
