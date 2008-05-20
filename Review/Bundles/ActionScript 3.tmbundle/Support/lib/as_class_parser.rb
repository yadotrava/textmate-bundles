# A Utilty class to convert an ActionScript class into
# list of it's constituent methods and properties.
#
# As long as the src is available, this will
# traverse the ancestry of the class adding all
# public and protected methods and properties.
class AsClassParser
    
    private
    
	def initialize
		
		@log = ""
		@depth = 0
		
		@src_dirs = []		
		@methods = []	
		@properties = []
		@privates = []
		
		@all_members = []
		
        #TODO: pickup all props in local scope only.
        #TODO: Filter class constants.
        #TODO: Filter objects. 
		
		@var_regexp = /^\s*(protected|public)\s+var\s+\b(\w+)\b\s*:\s*((\w+)|\*);/
		@method_regexp = /^\s*(override\s+)?(protected|public)\s+function\s+\b([a-z]\w+)\b\s*\(/
		@getset_regexp = /^\s*(protected|public)\s+function\s+\b(get|set)\b\s+\b(\w+)\b\s*\(/
        
        #TODO: Add Accessors.
		@static_method = /^\s*(public)\s+(static\s+)function\s+\b([a-z]\w+)\b\s*\(/
		@const_regexp = /^\s*\b(public|static)\b\s+\b(static|public)\b\s+\b(var|const)\b\s+\b(\w+)\b\s*:\s*((\w+)|\*)/

		@extends_regexp = /^\s*(public)\s+(dynamic\s+)?(final\s+)?(class|interface)\s+(\w+)\s+(extends)\s+(\w+)/
		
		create_src_list()
		
    end
    
    # Collects all of the src directories into a list.
    # The resulting list of dirs is then used when 
	# locating source files.
	def create_src_list
		@src_dirs = `find "$TM_PROJECT_DIRECTORY" -maxdepth 5 -name "src" -print`
		@src_dirs += "#{ENV['TM_BUNDLE_SUPPORT']}/data/src"
 	end
			
	# Finds the class in the filesystem.
	# If successful the class is loaded and returned.
	def load_class(path)
		@src_dirs.each { |d|
			uri = d.chomp + "/" + path
			#FIX: The assumption that we'll only find one match.
			if File.exists?(uri)
				return File.open(uri,"r" ).read.strip
			end
		}	
		nil
	end
	
	# Search and store the completions for doc.
	def parse_completions(doc)

		return if doc == nil

		@log += "Adding completions at level " + @depth.to_s + "\n"
		
		doc.each do |line|
			
			if line =~ @var_regexp
		  		@properties << $2.to_s  
			elsif line =~ @method_regexp
			    @methods << $3.to_s + "()"
			elsif line =~ @getset_regexp
			    @properties << $3.to_s
			end
			
		end
		
		@depth += 1
		
	end
	
	# Search and store the static completions for doc.
	def parse_statics(doc)
		
		return if doc == nil
		
		doc.each do |line|
			
			if line =~ @const_regexp
		  		@properties << $4.to_s  
			elsif line =~ @static_method
			    @methods << $3.to_s + "()"		   
			end
			
		end
		
	end
	
	# Add items to full list of properties.
	def add_to_all_members( items_to_add )
	    return if items_to_add == nil
	    if items_to_add.size > 0
	        @all_members.push('-') if @all_members.size > 0
	        @all_members = @all_members + items_to_add
	    end
	end
	
	# Loads and returns the superclass of the supllied doc.
	def load_parent_doc(doc)

		# Scan evidence of a superclass.
		doc.scan(@extends_regexp)
		
		# If we match then convert the import to a file reference.
		if $7 != nil			
			parent_path = doc_path_from_class_reference(doc,$7)
			return load_class( parent_path )			
		end
		
		return nil
	end
	
    public
    
	# Input Commands
	
	# Pass a class to start the ball rolling.
 	def add_doc(doc,local_scope)
		
		return if doc == nil
		
		# Add the methods and properties contained within the doc.
		parse_completions(doc)

		next_doc = load_parent_doc(doc);
		add_doc(next_doc,false)
		
 	end
    
    # Limit search to the static members of the specified class.
    def add_class(doc,reference)

		# ClassReferences.
		if reference =~ /^([A-Z]|\b(uint|int)\b)/
						
			path = doc_path_from_class_reference(doc,reference)
			@log += "Processing #{reference} as static. #{path}"
	        cdoc = load_class(path)
			parse_statics(cdoc) if cdoc != nil

		# Super.
		elsif reference =~ /^super$/
			
			super_class = load_parent_doc(doc)
			add_doc(super_class,false)

		# this.
		elsif reference =~ /^(this)?$/

			add_doc(doc,true)
		
		# Instance.
		else
			
			# TODO: Add get/set match.
			type_regexp = /^\s*(protected|public)\s+var\s+\b(#{reference})\b\s*:\s*((\w+)|\*);/
			local_type_regex = /^\s*var\s+(\b#{reference}\b)\s*:\s*(\w+)/
			
			type = determine_type_locally(doc,local_type_regex)
			type = determine_type(doc,type_regexp) if type == nil
			
			if type
				path = doc_path_from_class_reference(doc,type)
				cdoc = load_class(path)
				add_doc(cdoc,false) if cdoc != nil
			end
		end
		
		# TODO: Check type of method return statements.
		
    end
	
	# Searches the given document and determines the
	# document path for the given class_name reference.
	# Note, this relies on the reference being imported.
	def doc_path_from_class_reference(doc,class_name)

		# Use import statment to find our doc.
        doc.scan( /^\s*import\s+(([\w+\.]+)(\b#{class_name}\b))/)

        return $1.gsub(".","/")+".as" if $1 != nil

		# Assume it's top level.
		return class_name + ".as"
		
	end
	
	# Searches a document for the type of the specified property.
	def determine_type(doc,type_regexp)
		
		return if doc == nil
		
		# Search the document for the type.
		doc.scan(type_regexp)		
		return $3 if $3 != nil
		
		# Try the superclass.
		next_doc = load_parent_doc(doc);
		determine_type(next_doc,type_regexp);
		
	end

	# Searches the local scope for a var declaration
	# and returns it's type if found
	def determine_type_locally(doc,type_regexp)
		
		d = doc.split("\n")
		ln = ENV['TM_LINE_NUMBER'].to_i-1

		while ln > 0

		    txt = d[ln].to_s
			
			if txt =~ type_regexp
				
				return $2
				
			elsif txt =~ @method_regexp
				
				#When we hit a method statement exit.
				#TODO: Inspect arguments for type.
				return nil
				
			end
			
		    ln -= 1

		end
		
	end
	
    # Ouput Commands
    
    # Returns accumulated method completions.
    def methods
        
        return if @methods.empty?        
        @methods.uniq.sort
        
    end
	
	# Returns accumulated property completions.
	def properties
				
		return if @properties.empty?
		@properties.uniq.sort
		
	end
	
	# Returns accumulated private completions.
	# Only when working in a local scope.
	def privates
	   @privates.uniq.sort
	end
	
	# Returns any debug log data accumulated during parsing.
	def log
		@log
	end
	
	# Return a list of all members currently held.
	def all_members
		@all_members = []
		add_to_all_members(properties)
		add_to_all_members(methods)
		add_to_all_members(privates)
		return @all_members
	end
	
end