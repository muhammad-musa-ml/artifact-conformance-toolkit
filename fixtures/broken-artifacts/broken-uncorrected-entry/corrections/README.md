# corrections/ -- deliberately empty of fragments

CHECK-20 reads this directory for the record that says what a measurement did to
each claim. There is no fragment here, which is what makes every obligation in
this fixture unrecorded.

The README exists so the directory is COMMITTED. Git tracks files, not
directories, so an empty directory would be absent from a fresh clone -- and the
check would then resolve its records somewhere else and report a verdict about a
directory that is not this one.

`tools/assemble_records.py` names and counts anything here that is not a
fragment, so this file is visible in its output rather than silently skipped.
