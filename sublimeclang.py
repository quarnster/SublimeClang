"""
Copyright (c) 2011 Fredrik Ehnbom

This software is provided 'as-is', without any express or implied
warranty. In no event will the authors be held liable for any damages
arising from the use of this software.

Permission is granted to anyone to use this software for any purpose,
including commercial applications, and to alter it and redistribute it
freely, subject to the following restrictions:

   1. The origin of this software must not be misrepresented; you must not
   claim that you wrote the original software. If you use this software
   in a product, an acknowledgment in the product documentation would be
   appreciated but is not required.

   2. Altered source versions must be plainly marked as such, and must not be
   misrepresented as being the original software.

   3. This notice may not be removed or altered from any source
   distribution.
"""
from clang import cindex
import sublime_plugin
from sublime import Region
import sublime
import re

tu = None
index = None
class SublimeClangAutoComplete(sublime_plugin.EventListener):
    def on_query_completions(self, view, prefix, locations):
        global tu
        global index
        language = re.search("(?<=source\.)[a-zA-Z0-9+#]+", view.scope_name(locations[0])).group(0)
        if language != "c++" and language != "c":
            return []
        if tu == None:
            s = sublime.load_settings("clang.sublime-settings")
            index = cindex.Index.create()
            opts = []
            if s.has("options"):
                opts = s.get("options")
            tu = index.parse(view.file_name(), opts)
            #for diag in tu.diagnostics:
            #    print diag
        row,col = view.rowcol(locations[0])
        unsaved_files = []
        if view.is_dirty():
            unsaved_files.append((view.file_name(), str(view.substr(Region(0, 65536)))))
        res = tu.codeComplete(view.file_name(), row+1, col+1, unsaved_files)
        ret = []
        if res != None:
            for compRes in res.results:
                #print compRes.kind, compRes.string
                representation = ""
                insertion = ""
                add = False
                start = False;
                placeHolderCount = 0
                for chunk in compRes.string:
                    if chunk.isKindTypedText():
                        start = True
                        if chunk.spelling.startswith(prefix):
                            add = True
                    representation = "%s%s" % (representation, chunk.spelling)
                    if chunk.kind == cindex.completionChunkKindMap[15]:
                        representation = representation + " "
                    if start and not chunk.isKindInformative():
                        if chunk.isKindPlaceHolder():
                            placeHolderCount = placeHolderCount + 1
                            insertion = "%s${%d:%s}" % (insertion, placeHolderCount, chunk.spelling)
                        else: 
                            insertion = "%s%s" % (insertion, chunk.spelling)
                if add:
                    #print compRes.kind, compRes.string
                    ret.append((representation, insertion))
        return ret 

    def complete(self):
        if self.auto_complete:
            self.auto_complete = False
            self.view.window().run_command("auto_complete")


    def on_modified(self, view):
        self.auto_complete = False
        caret = view.sel()[0].a
        language = re.search("(?<=source\.)[a-zA-Z0-9+#]+", view.scope_name(caret))
        if language == None:
            return
        language = language.group(0)
        if language != "c++" and language != "c":
            return
        caret = view.sel()[0].a
        word = view.substr(view.word(caret))
        if word.endswith(".") or word.endswith("->") or word.endswith("::"):
            self.auto_complete = True
            self.view = view
            sublime.set_timeout(self.complete, 500)
