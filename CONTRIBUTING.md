# Before opening up a new issue
----------------------------------

* Use the search functionality to see if there's already an issue number
  dealing with the problem. If there is, please comment in the existing
  issue.
* Make sure that the issue hasn't already been fixed in the master branch.
  I don't create a new release of the plugin for every single commit so
  it is possible that the issue has already been fixed.
* Provide a small stand alone test case where the issue is reproducible.
* Make sure that the issue is with SublimeClang specifically and not
  something that's broken in Sublime Text 2 or libclang.

Please do remember that I am not your personal tech support and issues related
to configuring the plugin as appropriate for your system and target platform
have a high chance as being closed immediately. I am just a single person and
the time I allocate to this project is limited. You'll have a better
chance asking on the [Sublime Text 2 forums](http://www.sublimetext.com/forum/),
[Stackoverflow](http://stackoverflow.com/) or possibly
[Twitter](http://twitter.com/) to reach a much larger audience.

Having said that you can have a look at these existing issues to see
if they answer your issue or ask the community to help you out:

* [Issue 122](https://github.com/quarnster/SublimeClang/issues/122)
  for configuration issues getting the plugin to work on Windows.
* [Issue 35](https://github.com/quarnster/SublimeClang/issues/35)
  for configuration issues getting the plugin to work on Linux.
* [Issue 52](https://github.com/quarnster/SublimeClang/issues/52)
  for configuration issues getting the plugin to work when targeting iOS.
* [Issue 134](https://github.com/quarnster/SublimeClang/issues/134)
  for configuration issues getting the plugin to work when targeting the
  AVR toolchain.  

  
  
# Before submitting a pull request  
-----------------------------------

* Does the pull request fix a previously filed issue? If so, please do
  reference the issue number via #number in the commit message.
* Does the pull request fix an issue that has not previously been reported?
  Please explain what the issue is in the commit message.
* Make sure that no regressions are introduced and the unittests still pass.  
       `python unittests/unittest.py -disableplatformspecific`  
  Disabling the platformspecific tests just makes sure that there are no
  false failures due to differences in configuration between your
  platform/system/machine and mine.
* If appropriate, write a new unit test for the fix to catch future
  regressions.

