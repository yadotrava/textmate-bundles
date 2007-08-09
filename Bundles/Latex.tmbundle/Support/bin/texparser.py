import sys
import re
from os.path import basename
import os
import tmprefs
from urllib import quote
from struct import *


def percent_escape(str):
	return re.sub('[\x80-\xff /&]', lambda x: '%%%02X' % unpack('B', x.group(0))[0], str)

def make_link(file, line):
	return 'txmt://open?url=file:%2F%2F' + percent_escape(file) + '&line=' + line

def shell_quote(string):
	return '"' + re.sub(r'([`$\\"])', r'\\\1', string) + '"'


class TexParser(object):
    """Master Class for Parsing Tex Typsetting Streams"""
    def __init__(self, input_stream, verbose):
        super(TexParser, self).__init__()
        self.input_stream = input_stream
        self.patterns = []
        self.done = False
        self.verbose = verbose
        self.numErrs = 0
        self.numWarns = 0
        self.isFatal = False
        self.fileStack = []  #TODO: long term - can improve currentFile handling by keeping track of (xxx and )

    def parseStream(self):
        """Process the input_stream one line at a time, matching against
           each pattern in the patterns dictionary.  If a pattern matches
           call the corresponding method in the dictionary.  The dictionary
           is organized with patterns as the keys and methods as the values."""
        line = self.input_stream.readline()
        while line and not self.done:
            line = line.rstrip("\n")
            foundMatch = False

            # process matching patterns until we find one
            for pat,fun in self.patterns:
                myMatch = pat.match(line)
                if myMatch:
                    fun(myMatch,line)
                    sys.stdout.flush()
                    foundMatch = True
                    break
            if self.verbose and not foundMatch:
                print line
            
            line = self.input_stream.readline()
        if self.done == False:
            self.badRun()
        return self.isFatal, self.numErrs, self.numWarns

    def info(self,m,line):
        print '<p class="info">'
        print line
        print '</p>'

    def error(self,m,line):
        print '<p class="error">'
        print line
        print '</p>'
        self.numErrs += 1
        
    def warning(self,m,line):
        print '<p class="warning">'
        print line
        print '</p>'
        self.numWarns += 1

    def warn2(self,m,line):
        print '<p class="fmtWarning">'
        print line
        print '</p>'
        
    def fatal(self,m,line):
        print '<p class="error">'
        print line
        print '</p>'
        self.isFatal = True

    def badRun(self):
        """docstring for finishRun"""
        pass
        
class BibTexParser(TexParser):
    """Parse and format Error Messages from bibtex"""
    def __init__(self, btex, verbose):
        super(BibTexParser, self).__init__(btex,verbose)
        self.patterns += [ 
            (re.compile("Warning--I didn't find a database entry") , self.warning),
            (re.compile(r'I found no \\\w+ command') , self.error),
            (re.compile('This is BibTeX') , self.info),
            (re.compile('---') , self.finishRun)
        ]
    
    def finishRun(self,m,line):
        self.done = True
        print '</div>'

class LaTexParser(TexParser):
    """Parse Output From Latex"""
    def __init__(self, input_stream, verbose):
        super(LaTexParser, self).__init__(input_stream,verbose)
        self.patterns += [
            (re.compile('^This is') , self.info),
            (re.compile('^Document Class') , self.info),
            (re.compile('.*?\((\.\/[^\)]*?\.tex( |$))') , self.detectNewFile),
            (re.compile('.*\<use (.*?)\>') , self.detectInclude),
            (re.compile('^Output written') , self.info),
            (re.compile('LaTeX Warning:.*?input line (\d+)(\.|$)') , self.handleWarning),
            (re.compile('LaTeX Warning:.*') , self.partWarning),
            (re.compile('LaTeX Font Warning:.*') , self.warning),            
            (re.compile('Overfull.*wide') , self.warn2),
            (re.compile('Underfull.*badness') , self.warn2),                        
            (re.compile('^([\.\/\w\x7f-\xff ]+\.tex):(\d+):(.*)') , self.handleError),
            (re.compile('([^:]*):(\d+): LaTeX Error:(.*)') , self.handleError),
            (re.compile('([^:]*):(\d+): (Emergency stop)') , self.handleError),
            (re.compile('Transcript written on (.*)\.$') , self.finishRun),
            (re.compile('^Error: pdflatex') , self.pdfLatexError),
            (re.compile('\!.*') , self.handleOldStyleErrors),
            (re.compile('^\s+==>') , self.fatal)
        ]
                


    def detectNewFile(self,m,line):
        self.currentFile = m.group(1).rstrip()
        print "<h4>Processing: " + self.currentFile + "</h4>"

    def detectInclude(self,m,line):
        print "<ul><li>Including: " + m.group(1)
        print "</li></ul>"

    def handleWarning(self,m,line):
        print '<p class="warning"><a href="' + make_link(os.getcwd()+self.currentFile[1:], m.group(1)) + '">'+line+"</a></p>"
        self.numWarns += 1
    
    def partWarning(self,m,line):
        """Sometimes TeX breaks up warning output with hard linebreaks.  This is annoying
           Looking ahead one line seems perfectly safe.  In all the logs I have examined a warning
           always has a blank line after it.  So I'm pretty confident that eating an additional line is
           not going to unintentionally hide an important error.
        """
        newLine = line + self.input_stream.readline()
        newMatch = re.match('LaTeX Warning:.*?input line (\d+)(\.|$)',newLine)
        if newMatch:
            self.handleWarning(newMatch,newLine)
        else:
            self.warning(m,line)
    
    def handleError(self,m,line):
        print '<p class="error">'
        latexErrorMsg = 'Latex Error: <a class="error" href="' + make_link(os.getcwd()+'/'+m.group(1),m.group(2)) +  '">' + m.group(1)+":"+m.group(2) + '</a> '+m.group(3)
        line = self.input_stream.readline()
        while len(line) > 1:
            latexErrorMsg = latexErrorMsg+line
            line = self.input_stream.readline()
        print latexErrorMsg+'</p>'
        self.numErrs += 1
        
    def finishRun(self,m,line):
        logFile = m.group(1).strip('"')
        print '<p>  Complete transcript is in '
        print '<a href="' + make_link(os.getcwd()+'/'+logFile,'1') +  '">' + logFile + '</a>'
        print '</p>'
        self.done = True
        
    def handleOldStyleErrors(self,m,line):
        if re.search('[Ee]rror', line):
            print '<p class="error">'
            print line
            print '</p>'
            self.numErrs += 1
        else:
            print '<p class="warning">'
            print line
            print '</p>'
            self.numWarns += 1
        
    def pdfLatexError(self,m,line):
        """docstring for pdfLatexError"""
        self.numErrs += 1
        print '<p class="error">'
        print line
        line = self.input_stream.readline()
        if line and re.match('^ ==> Fatal error occurred', line):  
            print line.rstrip("\n")
            print '</p>'
            self.isFatal = True
        else:
            print '</p>'
        sys.stdout.flush()
    
    def badRun(self):
        """docstring for finishRun"""
        print '<p class="error">A fatal error occured, log file is in '
        logFile = os.path.basename(os.getenv('TM_FILEPATH'))
        logFile = logFile.replace('.tex','.log')
        print '<a href="' + make_link(os.getcwd()+'/'+logFile,'1') +  '">' + logFile + '</a>'        
        print '</p>'

class ParseLatexMk(TexParser):
    """docstring for ParseLatexMk"""
    def __init__(self, input_stream, verbose):
        super(ParseLatexMk, self).__init__(input_stream,verbose)

        self.patterns += [
            (re.compile('This is (pdfTeXk|latex2e|latex|XeTeXk)') , self.startLatex),
            (re.compile('This is BibTeX') , self.startBibtex),
            (re.compile('This is makeindex') , self.startBibtex),
            (re.compile('^Latexmk') , self.info),
            (re.compile('Run number') , self.newRun)
        ]
        self.numRuns = 0
    
    def startBibtex(self,m,line):
        print '<div class="bibtex">'
        print '<h3>' + line[:-1] + '</h3>'
        bp = BibTexParser(self.input_stream,self.verbose)
        f,e,w = bp.parseStream()
        self.numErrs += e
        self.numWarns += w

    def startLatex(self,m,line):
        print '<div class="latex">'
        print '<hr>'
        print '<h3>' + line[:-1] + '</h3>'
        bp = LaTexParser(self.input_stream,self.verbose)
        f,e,w = bp.parseStream()
        self.numErrs += e
        self.numWarns += w

    def newRun(self,m,line):
        print '<hr />'
        print '<p>', self.numErrs, 'Errors', self.numWarns, 'Warnings', 'in this run.', '</p>'
        self.numWarns = 0
        self.numErrs = 0
        self.numRuns += 1


if __name__ == '__main__':
    # test
    stream = open('../tex/test.log')
    lp = LaTexParser(stream,False)
    f,e,w = lp.parseStream()
    

