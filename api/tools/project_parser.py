import re
import os
import json
from datetime import datetime
import os
import argparse
import os
import argparse
import json
import sys
from urllib.parse import urlparse
from typing import Dict, List, Any
from api.tools.transfor_tokens import similarity_search
from api.config import get_embedder_config, is_ollama_embedder
class CodeParser:
    def __init__(self):

        self.patterns = {
            'python': {
                'class': r'^class\s+(\w+)(?:\(([^)]+)\))?:',
                'method': r'^\s+def\s+(\w+)\s*\(([^)]*)\)\s*(?:->\s*([\w\[\],\s]+))?\s*:',
                'function': r'^def\s+(\w+)\s*\(([^)]*)\)\s*(?:->\s*([\w\[\],\s]+))?\s*:',
                'import': r'^import\s+(.+)$',
                'from_import': r'^from\s+([\w\.]+)\s+import\s+(.+)'
            },
            'java': {
                'class': r'^\s*(?:public|private|protected)?\s*(?:abstract\s+)?(?:final\s+)?class\s+(\w+)',
                'method': r'^\s*((?:public|private|protected|static|final|abstract|synchronized|native|\s)*)([\w\<\>\[\]]+)\s+(\w+)\s*\(([^)]*)\)\s*(?:\{)?',
                'function': r'^\s*((?:public|private|protected|static|final|abstract|synchronized|native|\s)*)([\w\<\>\[\]]+)\s+(\w+)\s*\(([^)]*)\)\s*(?:\{)?',
                'import': r'^import\s+(?:static\s+)?([\w\.\*]+);'
            },
            'c_cpp': {
                'class': r'^\s*(?:class|struct)\s+(\w+)\s*(?::\s*(?:public|private|protected)\s+\w+)?\s*\{',
                'function': r'^\s*((?:[\w\s\*]+\s+)+)(\w+)\s*\(([^)]*)\)\s*\{',
                'include': r'^\s*#include\s+(?:<([^>]+)>|"([^"]+)")'
            },
            'javascript': {
                'class': r'^class\s+(\w+)(?:\s+extends\s+[\w]+)?\s*\{',
                'method': r'^\s*(\w+)\s*\(([^)]*)\)\s*\{',
                'function': r'^(?:function\s+)?(\w+)\s*\(([^)]*)\)\s*\{',
                'arrow_function': r'^\s*(?:const|let|var)\s+(\w+)\s*=\s*\(([^)]*)\)\s*=>',
                'import': r'^import\s+(?:(.+)\s+from\s+)?[\'"]([^\'"]+)[\'"]',
                'require': r'^\s*(?:const|let|var)\s+.+\s*=\s*require\([\'"]([^\'"]+)[\'"]\)'
            },
            'go': {
                'function': r'^func\s+(\w+)\s*\(([^)]*)\)\s*(?:\([^)]*\))?\s*\{',
                'method': r'^func\s+\(([^)]+)\)\s+(\w+)\s*\(([^)]*)\)\s*(?:\([^)]*\))?\s*\{',
                'import': r'^import\s+(?:(?:\()|(?:"([^"]+)"|`([^`]+)`|([^\s]+))',
                'package': r'^package\s+(\w+)'
            },
            'rust': {
                'function': r'^fn\s+(\w+)\s*\(([^)]*)\)\s*(?:->\s*([^{]+))?\s*\{',
                'struct': r'^(?:pub\s+)?struct\s+(\w+)\s*\{',
                'impl': r'^impl\s+(\w+)\s*\{',
                'use': r'^use\s+([^;]+);',
                'mod': r'^mod\s+(\w+)\s*\{'
            },
            'typescript': {
                'class': r'^class\s+(\w+)(?:\s+extends\s+[\w]+)?\s*\{',
                'method': r'^\s*(?:\w+\s+)?(\w+)\s*\(([^)]*)\)\s*(?::\s*([^{]+))?\s*\{',
                'function': r'^(?:function\s+)?(\w+)\s*\(([^)]*)\)\s*(?::\s*([^{]+))?\s*\{',
                'arrow_function': r'^\s*(?:const|let|var)\s+(\w+)\s*=\s*\(([^)]*)\)\s*(?::\s*([^{]+))?\s*=>',
                'interface': r'^interface\s+(\w+)\s*\{',
                'import': r'^import\s+(?:(.+)\s+from\s+)?[\'"]([^\'"]+)[\'"]',
                'require': r'^\s*(?:const|let|var)\s+.+\s*=\s*require\([\'"]([^\'"]+)[\'"]\)'
            },
            'php': {
                'class': r'^class\s+(\w+)(?:\s+extends\s+\w+)?(?:\s+implements\s+[^{]+)?\s*\{',
                'function': r'^function\s+(\w+)\s*\(([^)]*)\)\s*(?::\s*([^{]+))?\s*\{',
                'namespace': r'^namespace\s+([^;]+);',
                'use': r'^use\s+([^;]+);'
            },
            'swift': {
                'class': r'^class\s+(\w+)(?::\s*[^{]+)?\s*\{',
                'function': r'^func\s+(\w+)\s*\(([^)]*)\)\s*(?:->\s*([^{]+))?\s*\{',
                'import': r'^import\s+([^\n]+)'
            },
            'csharp': {
                'class': r'^\s*(?:public|private|protected|internal)?\s*(?:abstract\s+)?(?:sealed\s+)?class\s+(\w+)',
                'method': r'^\s*((?:public|private|protected|static|virtual|override|abstract|\s)*)([\w\<\>\[\]]+)\s+(\w+)\s*\(([^)]*)\)\s*(?:\{)?',
                'namespace': r'^namespace\s+([^{]+)\s*\{',
                'using': r'^using\s+([^;]+);'
            },
            'html': {
                'tag': r'^<(\w+)(?:\s+[^>]*)?>',
                'script': r'<script(?:\s+[^>]*)?>',
                'style': r'<style(?:\s+[^>]*)?>'
            },
            'css': {
                'selector': r'^([^{]+)\s*\{',
                'import': r'^@import\s+(?:url\()?["\']?([^"\'\)]+)["\']?\)?;'
            }
        }

    def detect_language(self, filename):

        ext = os.path.splitext(filename)[1].lower()
        language_map = {
            '.py': 'python',
            '.java': 'java',
            '.c': 'c_cpp',
            '.h': 'c_cpp',
            '.cpp': 'c_cpp',
            '.hpp': 'c_cpp',
            '.js': 'javascript',
            '.jsx': 'javascript',
            '.ts': 'typescript',
            '.tsx': 'typescript',
            '.go': 'go',
            '.rs': 'rust',
            '.php': 'php',
            '.swift': 'swift',
            '.cs': 'csharp'
        }
        return language_map.get(ext, 'unknown')

    def parse_code(self, filepath):

        try:
            language = self.detect_language(filepath)

            if language == 'go':
                return self._parse_go_file(filepath)

            with open(filepath, 'r', encoding='utf-8') as file:
                content = file.readlines()

            result = {
                'filename': os.path.basename(filepath),
                'language': language,
                'imports': [],
                'classes': [],
                'functions': []
            }

            current_class = None

            for i, line in enumerate(content):
                line = line.strip()


                if not line:
                    continue


                import_info = self._parse_imports(line, language, i)
                if import_info:
                    result['imports'].append(import_info)
                    continue


                if self._is_comment(line, language):
                    continue


                if language in self.patterns and 'class' in self.patterns[language]:
                    class_match = re.match(self.patterns[language]['class'], line)
                    if class_match:
                        class_name = class_match.group(1)
                        inheritance = class_match.group(2) if class_match.lastindex > 1 else None

                        current_class = {
                            'name': class_name,
                            'inheritance': inheritance,
                            'methods': [],
                            'line_number': i + 1
                        }
                        result['classes'].append(current_class)
                        continue


                function_info = None

                if language == 'python':
                    function_info = self._parse_python_function(line, i, current_class)
                elif language == 'java':
                    function_info = self._parse_java_function(line, i, current_class)
                elif language == 'c_cpp':
                    function_info = self._parse_c_cpp_function(line, i, current_class,language)
                elif language == 'javascript':
                    function_info = self._parse_javascript_function(line, i, current_class)
                elif language == 'typescript':
                    function_info = self._parse_typescript_function(line, i, current_class)
                elif language == 'go':
                    function_info = self._parse_go_function(line, i, current_class)
                elif language == 'rust':
                    function_info = self._parse_rust_function(line, i, current_class)
                elif language == 'php':
                    function_info = self._parse_php_function(line, i, current_class)
                elif language == 'swift':
                    function_info = self._parse_swift_function(line, i, current_class)
                elif language == 'csharp':
                    function_info = self._parse_csharp_function(line, i, current_class)
                elif language == 'html':
                    function_info = self._parse_html_element(line, i)
                elif language == 'css':
                    function_info = self._parse_css_selector(line, i)

                if function_info:
                    if current_class and function_info.get('is_method', False):
                        current_class['methods'].append(function_info)
                    else:
                        result['functions'].append(function_info)

            return result

        except Exception as e:
            return {'error': str(e)}

    def _is_comment(self, line, language):

        if language == 'python':
            return line.startswith('#')
        elif language in ['java', 'c_cpp', 'javascript', 'typescript', 'go', 'rust', 'php', 'swift', 'csharp']:
            return line.startswith('//') or line.startswith('/*') or line.startswith('*') or line.startswith('*/')
        elif language == 'html':
            return line.startswith('<!--')
        elif language == 'css':
            return line.startswith('/*')
        return False

    def _parse_imports(self, line, language, line_number):

        if language == 'python':

            import_match = re.match(self.patterns['python']['import'], line)
            if import_match:
                return {
                    'type': 'import',
                    'module': import_match.group(1),
                    'line_number': line_number + 1
                }


            from_import_match = re.match(self.patterns['python']['from_import'], line)
            if from_import_match:
                return {
                    'type': 'from_import',
                    'module': from_import_match.group(1),
                    'imports': from_import_match.group(2),
                    'line_number': line_number + 1
                }

        elif language == 'java':

            import_match = re.match(self.patterns['java']['import'], line)
            if import_match:
                return {
                    'type': 'import',
                    'package': import_match.group(1),
                    'line_number': line_number + 1
                }

        elif language == 'c_cpp':

            include_match = re.match(self.patterns['c_cpp']['include'], line)
            if include_match:

                included_file = include_match.group(1) or include_match.group(2)
                return {
                    'type': 'include',
                    'file': included_file,
                    'line_number': line_number + 1
                }

        elif language == 'javascript':

            import_match = re.match(self.patterns['javascript']['import'], line)
            if import_match:
                imports = import_match.group(1) or '*'
                module = import_match.group(2)
                return {
                    'type': 'import',
                    'imports': imports.strip(),
                    'module': module,
                    'line_number': line_number + 1
                }


            require_match = re.match(self.patterns['javascript']['require'], line)
            if require_match:
                return {
                    'type': 'require',
                    'module': require_match.group(1),
                    'line_number': line_number + 1
                }

        elif language == 'typescript':

            import_match = re.match(self.patterns['typescript']['import'], line)
            if import_match:
                imports = import_match.group(1) or '*'
                module = import_match.group(2)
                return {
                    'type': 'import',
                    'imports': imports.strip(),
                    'module': module,
                    'line_number': line_number + 1
                }


            require_match = re.match(self.patterns['typescript']['require'], line)
            if require_match:
                return {
                    'type': 'require',
                    'module': require_match.group(1),
                    'line_number': line_number + 1
                }

        elif language == 'go':

            import_match = re.match(self.patterns['go']['import'], line)
            if import_match:
                # Go的import有多种格式，这里简化处理
                import_path = import_match.group(1) or import_match.group(2) or import_match.group(3)
                return {
                    'type': 'import',
                    'package': import_path,
                    'line_number': line_number + 1
                }


            package_match = re.match(self.patterns['go']['package'], line)
            if package_match:
                return {
                    'type': 'package',
                    'name': package_match.group(1),
                    'line_number': line_number + 1
                }

        elif language == 'rust':

            use_match = re.match(self.patterns['rust']['use'], line)
            if use_match:
                return {
                    'type': 'use',
                    'module': use_match.group(1),
                    'line_number': line_number + 1
                }


            mod_match = re.match(self.patterns['rust']['mod'], line)
            if mod_match:
                return {
                    'type': 'mod',
                    'name': mod_match.group(1),
                    'line_number': line_number + 1
                }

        elif language == 'php':

            namespace_match = re.match(self.patterns['php']['namespace'], line)
            if namespace_match:
                return {
                    'type': 'namespace',
                    'name': namespace_match.group(1),
                    'line_number': line_number + 1
                }


            use_match = re.match(self.patterns['php']['use'], line)
            if use_match:
                return {
                    'type': 'use',
                    'name': use_match.group(1),
                    'line_number': line_number + 1
                }

        elif language == 'swift':
            # 解析 Swift import
            import_match = re.match(self.patterns['swift']['import'], line)
            if import_match:
                return {
                    'type': 'import',
                    'module': import_match.group(1),
                    'line_number': line_number + 1
                }

        elif language == 'csharp':
            # 解析 C# using
            using_match = re.match(self.patterns['csharp']['using'], line)
            if using_match:
                return {
                    'type': 'using',
                    'namespace': using_match.group(1),
                    'line_number': line_number + 1
                }

            # 解析 C# namespace
            namespace_match = re.match(self.patterns['csharp']['namespace'], line)
            if namespace_match:
                return {
                    'type': 'namespace',
                    'name': namespace_match.group(1),
                    'line_number': line_number + 1
                }

        elif language == 'css':
            # 解析 CSS import
            import_match = re.match(self.patterns['css']['import'], line)
            if import_match:
                return {
                    'type': 'import',
                    'file': import_match.group(1),
                    'line_number': line_number + 1
                }

        return None

    def _parse_python_function(self, line, line_number, current_class):
        """解析Python函数和方法"""
        patterns_to_try = []

        if current_class:
            patterns_to_try.append(self.patterns['python']['method'])
        patterns_to_try.append(self.patterns['python']['function'])

        for pattern in patterns_to_try:
            match = re.match(pattern, line)
            if match:
                func_name = match.group(1)
                params = match.group(2)
                return_type = match.group(3) if match.lastindex > 2 else None

                return {
                    'name': func_name,
                    'parameters': params,
                    'return_type': return_type,
                    'line_number': line_number + 1,
                    'is_method': current_class is not None
                }
        return None

    def _parse_java_function(self, line, line_number, current_class):
        """解析Java函数和方法"""
        patterns_to_try = []

        if current_class:
            patterns_to_try.append(self.patterns['java']['method'])
        patterns_to_try.append(self.patterns['java']['function'])

        for pattern in patterns_to_try:
            match = re.match(pattern, line)
            if match:
                modifiers = match.group(1).strip()
                return_type = match.group(2).strip()
                func_name = match.group(3)
                params = match.group(4) if match.lastindex > 3 else ""

                return {
                    'name': func_name,
                    'parameters': params,
                    'return_type': return_type,
                    'modifiers': modifiers,
                    'line_number': line_number + 1,
                    'is_method': current_class is not None
                }
        return None

    def _parse_c_cpp_function(self, line, line_number, current_class,language):
        """解析C/C++函数"""
        # 如果是C++，可能有类方法
        if current_class and language == 'c_cpp':
            # 简化处理，假设在类定义后的函数都是方法
            match = re.match(self.patterns['c_cpp']['function'], line)
            if match:
                return_type = match.group(1).strip()
                func_name = match.group(2)
                params = match.group(3) if match.lastindex > 2 else ""

                return {
                    'name': func_name,
                    'parameters': params,
                    'return_type': return_type,
                    'line_number': line_number + 1,
                    'is_method': True
                }
        else:
            # 普通函数
            match = re.match(self.patterns['c_cpp']['function'], line)
            if match:
                return_type = match.group(1).strip()
                func_name = match.group(2)
                params = match.group(3) if match.lastindex > 2 else ""

                return {
                    'name': func_name,
                    'parameters': params,
                    'return_type': return_type,
                    'line_number': line_number + 1,
                    'is_method': False
                }
        return None

    def _parse_javascript_function(self, line, line_number, current_class):
        """解析JavaScript函数和方法"""
        patterns_to_try = []

        if current_class:
            patterns_to_try.append(self.patterns['javascript']['method'])

        patterns_to_try.extend([
            self.patterns['javascript']['function'],
            self.patterns['javascript']['arrow_function']
        ])

        for pattern in patterns_to_try:
            match = re.match(pattern, line)
            if match:
                func_name = match.group(1)
                params = match.group(2) if match.lastindex > 1 else ""

                # JavaScript是动态类型语言，通常没有明确的返回类型声明
                return_type = self._infer_javascript_return_type(func_name)

                return {
                    'name': func_name,
                    'parameters': params,
                    'return_type': return_type,
                    'line_number': line_number + 1,
                    'is_method': current_class is not None and pattern != self.patterns['javascript']['arrow_function']
                }
        return None

    def _parse_typescript_function(self, line, line_number, current_class):
        """解析TypeScript函数和方法"""
        patterns_to_try = []

        if current_class:
            patterns_to_try.append(self.patterns['typescript']['method'])

        patterns_to_try.extend([
            self.patterns['typescript']['function'],
            self.patterns['typescript']['arrow_function']
        ])

        for pattern in patterns_to_try:
            match = re.match(pattern, line)
            if match:
                func_name = match.group(1)
                params = match.group(2) if match.lastindex > 1 else ""
                return_type = match.group(3) if match.lastindex > 2 else None

                return {
                    'name': func_name,
                    'parameters': params,
                    'return_type': return_type,
                    'line_number': line_number + 1,
                    'is_method': current_class is not None and pattern != self.patterns['typescript']['arrow_function']
                }
        return None

    def _parse_go_file(self, filepath):
        """专门解析Go语言文件"""
        try:
            with open(filepath, 'r', encoding='utf-8') as file:
                content = file.readlines()

            result = {
                'filename': os.path.basename(filepath),
                'language': 'go',
                'imports': [],
                'functions': [],
                'methods': [],
                'package': None
            }

            in_import_block = False
            in_comment_block = False

            for i, line in enumerate(content):
                line = line.strip()

                # 处理多行注释
                if '/*' in line and '*/' not in line:
                    in_comment_block = True
                    continue
                if in_comment_block:
                    if '*/' in line:
                        in_comment_block = False
                    continue
                if in_comment_block:
                    continue

                # 跳过空行和单行注释
                if not line or line.startswith('//'):
                    continue

                # 解析package声明
                package_match = re.match(r'^package\s+(\w+)', line)
                if package_match:
                    result['package'] = package_match.group(1)
                    continue

                # 检查是否进入多行import块
                if line == 'import (':
                    in_import_block = True
                    continue

                # 如果在import块中
                if in_import_block:
                    if line == ')':
                        in_import_block = False
                        continue

                    # 解析import路径 - 更宽松的匹配
                    import_match = re.search(r'["`]([^"`]+)["`]', line)
                    if import_match:
                        result['imports'].append({
                            'type': 'import',
                            'path': import_match.group(1),
                            'line_number': i + 1
                        })
                    continue

                # 解析单行import语句
                import_match = re.match(r'^import\s+(?:"([^"]+)"|`([^`]+)`|([^\s;]+))', line)
                if import_match:
                    import_path = import_match.group(1) or import_match.group(2) or import_match.group(3)
                    if import_path:
                        result['imports'].append({
                            'type': 'import',
                            'path': import_path,
                            'line_number': i + 1
                        })
                    continue

                # 解析函数定义
                func_match = re.match(r'^func\s+(\w+)\s*\(([^)]*)\)\s*(?:\(([^)]*)\))?\s*(?:\{|$)', line)
                if func_match:
                    func_name = func_match.group(1)
                    params = func_match.group(2).strip()
                    return_types = func_match.group(3).strip() if func_match.group(3) else ""

                    result['functions'].append({
                        'name': func_name,
                        'parameters': params,
                        'return_types': return_types,
                        'line_number': i + 1,
                        'type': 'function'
                    })
                    continue

                # 解析方法定义（带接收器）
                method_match = re.match(r'^func\s+\(([^)]+)\)\s+(\w+)\s*\(([^)]*)\)\s*(?:\(([^)]*)\))?\s*(?:\{|$)',
                                        line)
                if method_match:
                    receiver = method_match.group(1).strip()
                    method_name = method_match.group(2)
                    params = method_match.group(3).strip()
                    return_types = method_match.group(4).strip() if method_match.group(4) else ""

                    result['methods'].append({
                        'name': method_name,
                        'receiver': receiver,
                        'parameters': params,
                        'return_types': return_types,
                        'line_number': i + 1,
                        'type': 'method'
                    })
                    continue

            return result

        except Exception as e:
            return {'error': str(e), 'file': filepath}
    def _parse_go_function(self, line, line_number, current_class):
        """解析Go函数和方法 - 修复版本"""
        # Go没有类的概念，所以current_class应该总是None
        # 普通函数
        func_match = re.match(r'^func\s+(\w+)\s*\(([^)]*)\)\s*(?:\(([^)]*)\))?\s*\{', line)
        if func_match:
            func_name = func_match.group(1)
            params = func_match.group(2).strip()
            return_types = func_match.group(3).strip() if func_match.group(3) else ""

            return {
                'name': func_name,
                'parameters': params,
                'return_types': return_types,
                'line_number': line_number + 1,
                'is_method': False
            }

        # 方法（带接收器）
        method_match = re.match(r'^func\s+\(([^)]+)\)\s+(\w+)\s*\(([^)]*)\)\s*(?:\(([^)]*)\))?\s*\{', line)
        if method_match:
            receiver = method_match.group(1).strip()
            method_name = method_match.group(2)
            params = method_match.group(3).strip()
            return_types = method_match.group(4).strip() if method_match.group(4) else ""

            return {
                'name': method_name,
                'parameters': params,
                'receiver': receiver,
                'return_types': return_types,
                'line_number': line_number + 1,
                'is_method': True
            }

        return None
    def _parse_rust_function(self, line, line_number, current_class):
        """解析Rust函数"""
        match = re.match(self.patterns['rust']['function'], line)
        if match:
            func_name = match.group(1)
            params = match.group(2) if match.lastindex > 1 else ""
            return_type = match.group(3) if match.lastindex > 2 else None

            return {
                'name': func_name,
                'parameters': params,
                'return_type': return_type,
                'line_number': line_number + 1,
                'is_method': False
            }
        return None

    def _parse_php_function(self, line, line_number, current_class):
        """解析PHP函数和方法"""
        match = re.match(self.patterns['php']['function'], line)
        if match:
            func_name = match.group(1)
            params = match.group(2) if match.lastindex > 1 else ""
            return_type = match.group(3) if match.lastindex > 2 else None

            return {
                'name': func_name,
                'parameters': params,
                'return_type': return_type,
                'line_number': line_number + 1,
                'is_method': current_class is not None
            }
        return None

    def _parse_swift_function(self, line, line_number, current_class):
        """解析Swift函数和方法"""
        match = re.match(self.patterns['swift']['function'], line)
        if match:
            func_name = match.group(1)
            params = match.group(2) if match.lastindex > 1 else ""
            return_type = match.group(3) if match.lastindex > 2 else None

            return {
                'name': func_name,
                'parameters': params,
                'return_type': return_type,
                'line_number': line_number + 1,
                'is_method': current_class is not None
            }
        return None

    def _parse_csharp_function(self, line, line_number, current_class):
        """解析C#函数和方法"""
        match = re.match(self.patterns['csharp']['method'], line)
        if match:
            modifiers = match.group(1).strip()
            return_type = match.group(2).strip()
            func_name = match.group(3)
            params = match.group(4) if match.lastindex > 3 else ""

            return {
                'name': func_name,
                'parameters': params,
                'return_type': return_type,
                'modifiers': modifiers,
                'line_number': line_number + 1,
                'is_method': current_class is not None
            }
        return None

    def _parse_html_element(self, line, line_number):
        """解析HTML元素"""
        match = re.match(self.patterns['html']['tag'], line)
        if match:
            tag_name = match.group(1)

            # 跳过自闭合标签和结束标签
            if tag_name.startswith('/') or line.endswith('/>'):
                return None

            return {
                'name': tag_name,
                'type': 'html_tag',
                'line_number': line_number + 1
            }

        # 检查script标签
        script_match = re.match(self.patterns['html']['script'], line)
        if script_match:
            return {
                'name': 'script',
                'type': 'script_tag',
                'line_number': line_number + 1
            }

        # 检查style标签
        style_match = re.match(self.patterns['html']['style'], line)
        if style_match:
            return {
                'name': 'style',
                'type': 'style_tag',
                'line_number': line_number + 1
            }

        return None

    def _parse_css_selector(self, line, line_number):
        """解析CSS选择器"""
        match = re.match(self.patterns['css']['selector'], line)
        if match:
            selector = match.group(1).strip()

            return {
                'name': selector,
                'type': 'css_selector',
                'line_number': line_number + 1
            }

        return None

    def _infer_javascript_return_type(self, func_name):
        """根据函数名推断JavaScript返回类型"""
        if func_name.startswith('get') or func_name.startswith('is') or func_name.startswith('has'):
            return 'boolean'
        elif func_name.startswith('create') or func_name.startswith('make'):
            return 'object'
        elif func_name.startswith('calculate') or func_name.startswith('compute'):
            return 'number'
        elif func_name.startswith('to') and len(func_name) > 2:
            return func_name[2:].lower()  # toString -> string, toNumber -> number
        return 'any'

    def print_results(self, result, output_file=None):
        """将解析结果转换为LLM易于理解的JSON格式"""

        # 构建基础结果结构
        output_data = {
            "metadata": {
                "filename": result.get('filename', ''),
                "language": result.get('language', ''),
            }
        }

        if 'error' in result:
            output_data["error"] = {
                "message": result['error'],
                "file": result.get('file', '')
            }

            # 输出到控制台
            print(json.dumps(output_data, indent=2, ensure_ascii=False))

            # 保存到文件（如果指定了输出文件）
            if output_file:
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(output_data, f, indent=2, ensure_ascii=False)
            return output_data

        # 构建成功解析的数据结构
        parsed_data = {}

        # 添加package信息
        if result.get('package'):
            parsed_data["package"] = result['package']

        # 统一import信息结构
        if result.get('imports'):
            parsed_data["imports"] = []
            for imp in result['imports']:
                import_info = {
                    "type": imp['type'],
                    "line_number": imp['line_number']
                }
                # 统一使用"import_path"作为导入路径的key
                if 'path' in imp:
                    import_info["import_path"] = imp['path']
                if 'module' in imp:
                    import_info["import_path"] = imp['module']
                if 'imports' in imp:
                    import_info["import_path"] = imp['imports']
                if 'package' in imp:
                    import_info["import_path"] = imp['package']
                parsed_data["imports"].append(import_info)

        # 统一函数和方法的数据结构
        parsed_data["functions"] = []
        parsed_data["methods"] = []

        # 处理Go语言的函数和方法
        if result['language'] == 'go':
            for func in result.get('functions', []):
                func_info = {
                    "name": func['name'],
                    "type": "function",
                    "parameters": func['parameters'],
                    "line_number": func['line_number'],
                    "signature": f"func {func['name']}({func['parameters']})"
                }
                if func.get('return_types'):
                    func_info["return_type"] = func['return_types']  # 统一使用return_type
                    func_info["signature"] += f" -> ({func['return_types']})"
                parsed_data["functions"].append(func_info)

            for method in result.get('methods', []):
                method_info = {
                    "name": method['name'],
                    "type": "method",
                    "receiver": method['receiver'],
                    "parameters": method['parameters'],
                    "line_number": method['line_number'],
                    "signature": f"func ({method['receiver']}) {method['name']}({method['parameters']})"
                }
                if method.get('return_types'):
                    method_info["return_type"] = method['return_types']  # 统一使用return_type
                    method_info["signature"] += f" -> ({method['return_types']})"
                parsed_data["methods"].append(method_info)

        # 处理其他语言（Java、Python等）
        else:
            parsed_data["classes"] = []
            for cls in result.get('classes', []):
                class_info = {
                    "name": cls['name'],
                    "line_number": cls['line_number'],
                    "methods": []
                }
                if cls.get('inheritance'):
                    class_info["inheritance"] = cls['inheritance']

                for method in cls.get('methods', []):
                    method_info = {
                        "name": method['name'],
                        "type": "method",
                        "parameters": method['parameters'],
                        "line_number": method['line_number'],
                        "signature": f"{method['name']}({method['parameters']})"
                    }
                    if method.get('return_type'):
                        method_info["return_type"] = method['return_type']
                        method_info["signature"] += f" -> {method['return_type']}"
                    if method.get('modifiers'):
                        method_info["modifiers"] = method['modifiers']
                    if method.get('receiver'):
                        method_info["receiver"] = method['receiver']
                        method_info["signature"] = f"({method['receiver']}) {method_info['signature']}"

                    class_info["methods"].append(method_info)
                    # 同时添加到顶层的methods列表中
                    parsed_data["methods"].append(method_info)

                parsed_data["classes"].append(class_info)

            for func in result.get('functions', []):
                func_info = {
                    "name": func['name'],
                    "type": "function",
                    "parameters": func['parameters'],
                    "line_number": func['line_number'],
                    "signature": f"{func['name']}({func['parameters']})"
                }
                if func.get('return_type'):
                    func_info["return_type"] = func['return_type']
                    func_info["signature"] += f" -> {func['return_type']}"
                if func.get('modifiers'):
                    func_info["modifiers"] = func['modifiers']
                if func.get('receiver'):
                    func_info["receiver"] = func['receiver']
                    func_info["signature"] = f"({func['receiver']}) {func_info['signature']}"
                if func.get('type'):
                    func_info["function_type"] = func['type']

                parsed_data["functions"].append(func_info)

        # 添加统计信息
        stats = {
            "total_imports": len(parsed_data.get('imports', [])),
            "total_classes": len(parsed_data.get('classes', [])),
            "total_functions": len(parsed_data.get('functions', [])),
            "total_methods": len(parsed_data.get('methods', []))
        }

        output_data["parsed_data"] = parsed_data
        output_data["statistics"] = stats

        # 输出到控制台
        print(json.dumps(output_data, indent=2, ensure_ascii=False))

        # 保存到文件（如果指定了输出文件）
        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, indent=2, ensure_ascii=False)

        return output_data


import os
import json
def get_analysis_default_root_path():
    adalflow_dir = os.path.expanduser(os.path.join("~", ".adalflow"))

    # 创建缓存目录路径
    analysis_dir = os.path.join(adalflow_dir, "analysis")


    # 确保缓存目录存在，如果不存在则创建
    try:
        os.makedirs(analysis_dir, exist_ok=True)
        print(f"缓存目录已就绪: {analysis_dir}")
    except OSError as e:
        print(f"无法创建缓存目录 {analysis_dir}: {e}")
    return analysis_dir

def extract_dependencies(imports: List[Dict]) -> List[str]:
    """提取依赖信息"""
    dependencies = set()
    for imp in imports:
        # 尝试从多个可能的字段中获取依赖信息
        for key in ["import_path", "path", "module", "package", "imports"]:
            if key in imp and imp[key]:
                dependencies.add(imp[key])
                break
    return list(dependencies)


def extract_dependencies(imports: List[Dict]) -> List[str]:
    """提取依赖信息"""
    dependencies = set()
    for imp in imports:
        if "import_path" in imp:
            dependencies.add(imp["import_path"])
        elif "path" in imp:
            dependencies.add(imp["path"])
    return list(dependencies)  # 只取前10个依赖

def extract_key_info(project_data: Dict) -> Dict:
    """从项目数据中提取关键信息（简洁版）"""

    def safe_get(data, *keys, default=None):
        """安全获取嵌套字典的值"""
        for key in keys:
            try:
                data = data[key]
            except (KeyError, TypeError):
                return default
        return data

    simplified_data = {
        "project_name": safe_get(project_data, "project_name", default=""),
        "total_files": safe_get(project_data, "total_files", default=0),
        "modules": {}
    }

    for file_info in safe_get(project_data, "files", default=[]):
        analysis = safe_get(file_info, "analysis_result", default={})
        parsed_data = safe_get(analysis, "parsed_data", default={})

        file_type = safe_get(file_info, "file_type", default="unknown")
        file_name = safe_get(file_info, "file_name", default="unknown")

        if file_type not in simplified_data["modules"]:
            simplified_data["modules"][file_type] = {"file_count": 0, "files": []}

        file_summary = {
            "file_name": file_name,
            "language": safe_get(analysis, "metadata", "language", default="unknown"),
            "key_classes": [],
            "key_functions": [],
            "imports_count": safe_get(analysis, "statistics", "total_imports", default=0),
            "dependencies": extract_dependencies(safe_get(parsed_data, "imports", default=[]))
        }

        # 处理类信息
        for cls in safe_get(parsed_data, "classes", default=[]):
            class_info = {
                "name": safe_get(cls, "name", default="unknown"),
                "methods": [safe_get(method, "name", default="unknown")
                            for method in safe_get(cls, "methods", default=[])[:50]],
                "method_count": len(safe_get(cls, "methods", default=[]))
            }
            file_summary["key_classes"].append(class_info)

        # 处理函数信息
        for func in safe_get(parsed_data, "functions", default=[]):
            func_info = {
                "name": safe_get(func, "name", default="unknown"),
                "parameters": safe_get(func, "parameters", default=""),
                "return_type": safe_get(func, "return_type", default="unknown")
            }
            file_summary["key_functions"].append(func_info)

        simplified_data["modules"][file_type]["files"].append(file_summary)
        simplified_data["modules"][file_type]["file_count"] += 1

    return simplified_data


def get_structural_analysis(project_directory):
    if not os.path.isabs(project_directory):
        project_directory = os.path.abspath(project_directory)
    # 检查目录是否存在
    if not os.path.isdir(project_directory):
        print(f"Error: Directory '{project_directory}' does not exist or is not a directory")
        exit(1)
    output_extract_filename = f"{os.path.basename(project_directory)}_project_extract_analysis.json"
    output_extract_path = os.path.join(get_analysis_default_root_path(), output_extract_filename)

    # 4. 读取并返回内容
    if not os.path.isfile(output_extract_path):
        print(f"Warning: Analysis file '{output_extract_path}' not found, returning empty dict.")
        return {}

    try:
        # 检查文件大小
        file_size = os.path.getsize(output_extract_path)
        max_size = 400 * 1024  # 400 KiB

        if file_size > max_size:
            print(f"Warning: Analysis file '{output_extract_path}' is too large ({file_size} bytes), "
                  f"reading only first {max_size} bytes.")
            with open(output_extract_path, "r", encoding="utf-8") as f:
                # 只读取前400KiB内容
                partial_content = f.read(max_size)
                # 尝试解析部分内容为JSON
                data = json.loads(partial_content)
        else:
            with open(output_extract_path, "r", encoding="utf-8") as f:
                data = json.load(f)

        return data
    except (OSError, json.JSONDecodeError) as e:
        print(f"Error reading or parsing '{output_extract_path}': {e}", file=sys.stderr)
        return {}

def save_summarize_json(project_directory,summarize_text):
    if not os.path.isabs(project_directory):
        project_directory = os.path.abspath(project_directory)
    # 检查目录是否存在
    if not os.path.isdir(project_directory):
        print(f"Error: Directory '{project_directory}' does not exist or is not a directory")
        exit(1)
    summarize_filename = f"{os.path.basename(project_directory)}_project_summarize_text.json"
    summarize_path = os.path.join(get_analysis_default_root_path(), summarize_filename)
    # 确保目标目录存在
    os.makedirs(os.path.dirname(summarize_path), exist_ok=True)

    # 写入 JSON 文件
    with open(summarize_path, 'w', encoding='utf-8') as f:
        json.dump(summarize_text, f, ensure_ascii=False, indent=2)

    print(f"Summarize text saved to: {summarize_path}")
def get_summarize_json(repo_name):
    summarize_filename = f"{repo_name}_project_summarize_text.json"
    summarize_path = os.path.join(get_analysis_default_root_path(), summarize_filename)
    if not os.path.isfile(summarize_path):
        print(f"Warning: Analysis file '{summarize_path}' not found, returning empty dict.")
        return {}

    try:
        with open(summarize_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data
    except (OSError, json.JSONDecodeError) as e:
        print(f"Error reading or parsing '{summarize_path}': {e}", file=sys.stderr)
        return {}


def save_java_callgraph(project_directory):
    if not os.path.isabs(project_directory):
        project_directory = os.path.abspath(project_directory)
    # 检查目录是否存在
    if not os.path.isdir(project_directory):
        print(f"Error: Directory '{project_directory}' does not exist or is not a directory")
        exit(1)
    if not os.path.isdir(project_directory):
        print(f"Error: Directory '{project_directory}' does not exist or is not a directory")
        exit(1)
    summarize_filename = f"{os.path.basename(project_directory)}_java_call_chain.json"
    summarize_path = os.path.join(get_analysis_default_root_path(), summarize_filename)
    # 确保目标目录存在
    from api.config import get_embedder_config, is_ollama_embedder
    os.makedirs(os.path.dirname(summarize_path), exist_ok=True)
    from api.tools.java_callgraph import analyze_java_callgraph
    analyze_java_callgraph(project_directory,summarize_path)




def get_java_callgraph(query: str,repo_name: str,):
    summarize_filename = f"{repo_name}_java_call_chain.json"
    summarize_path = os.path.join(get_analysis_default_root_path(), summarize_filename)
    if not os.path.isfile(summarize_path):
        return {}
    #获取向量
    if  os.path.getsize(summarize_path) > 500 * 1024:
        print("==================get_java_callgraph============="+query)
        summarize_filename_faiss_store = f"{repo_name}_faiss_store"
        faiss_store_path = os.path.join(get_analysis_default_root_path(), summarize_filename_faiss_store)
        the_similarity_search =  similarity_search(summarize_path,query,faiss_store_path,30,is_ollama_embedder())

        return the_similarity_search
    else:
        summarize_filename = f"{repo_name}_java_call_chain.json"
        summarize_path = os.path.join(get_analysis_default_root_path(), summarize_filename)

        if not os.path.isfile(summarize_path):
            print(f"Warning: Analysis file '{summarize_path}' not found, returning empty dict.")
            return {}

        try:
            with open(summarize_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data
        except (OSError, json.JSONDecodeError) as e:
            print(f"Error reading or parsing '{summarize_path}': {e}", file=sys.stderr)
            return {}

def extract_owner_repo(repo_url):
    """
    从 GitHub / GitLab / Bitbucket URL 或纯 owner/repo 格式提取 owner 和 repo，并返回 owner_repo 格式字符串
    支持格式如：
      - https://github.com/owner/repo
      - https://gitlab.com/owner/repo
      - https://bitbucket.org/owner/repo       ← 新增支持！
      - git@github.com:owner/repo.git
      - git@gitlab.com:owner/repo.git
      - git@bitbucket.org:owner/repo.git      ← 新增支持！
      - git://github.com/owner/repo.git
      - owner/repo
      - owner/repo.git
    """
    repo_url = repo_url.strip()  # 去除首尾空格

    # 情况1：SSH 格式 git@host:owner/repo.git
    if repo_url.startswith("git@"):
        parts = repo_url.split(":", 1)
        if len(parts) != 2:
            raise ValueError("Invalid SSH URL format")
        host_part, path_part = parts

        # 支持 GitHub / GitLab / Bitbucket
        if not any(host_part.endswith(domain) for domain in ("github.com", "gitlab.com", "bitbucket.org")):
            raise ValueError("Unsupported Git host in SSH URL")

        path = path_part.rstrip(".git")
        path_parts = path.split("/", 1)
        if len(path_parts) != 2:
            raise ValueError("Invalid path in SSH URL: owner/repo expected")
        owner, repo = path_parts

    # 情况2：HTTP/HTTPS 或 git:// URL
    elif "://" in repo_url:
        parsed = urlparse(repo_url)
        if not parsed.netloc:
            raise ValueError("Invalid URL: no host found")

        # 支持三大平台
        supported_hosts = {"github.com", "gitlab.com", "bitbucket.org"}
        if parsed.netloc not in supported_hosts:
            raise ValueError(f"Unsupported Git host: {parsed.netloc}")

        path = parsed.path.strip("/")
        if path.endswith(".git"):
            path = path[:-4]  # 去掉 .git 后缀

        parts = path.split("/", 2)
        if len(parts) < 2:
            raise ValueError("Invalid URL: owner or repo not found")
        owner, repo = parts[0], parts[1]

    # 情况3：纯 owner/repo 格式
    else:
        if "/" not in repo_url:
            raise ValueError("Invalid format: expected 'owner/repo'")

        if repo_url.endswith(".git"):
            repo_url = repo_url[:-4]  # 去掉 .git 后缀

        parts = repo_url.split("/", 1)
        if len(parts) != 2:
            raise ValueError("Invalid format: expected exactly one '/' separator")

        owner, repo = parts[0], parts[1]

        if not owner or not repo:
            raise ValueError("Owner or repo name is empty")

    return f"{owner}_{repo}"

def parse_project(project_directory):
    # 获取当前脚本文件所在的目录
    # 确保项目目录是绝对路径
    if not os.path.isabs(project_directory):
        project_directory = os.path.abspath(project_directory)

    code_parser = CodeParser()

    # 定义支持的文件后缀映射
    language_map = {
        '.py': 'python',
        '.java': 'java',
        '.c': 'c_cpp',
        '.h': 'c_cpp',
        '.cpp': 'c_cpp',
        '.hpp': 'c_cpp',
        '.js': 'javascript',
        '.jsx': 'javascript',
        '.ts': 'typescript',
        '.tsx': 'typescript',
        '.go': 'go',
        '.rs': 'rust',
        '.php': 'php',
        '.swift': 'swift',
        '.cs': 'csharp'
    }

    # 获取所有支持的后缀名
    supported_extensions = set(language_map.keys())

    # 检查目录是否存在
    if not os.path.isdir(project_directory):
        print(f"Error: Directory '{project_directory}' does not exist or is not a directory")
        exit(1)

    # 创建项目级的JSON数据结构
    project_data = {
        "project_name": os.path.basename(project_directory),
        "project_path": project_directory,
        "total_files": 0,
        "processed_files": 0,
        "files": []
    }

    # 遍历目录下的所有文件
    for root, dirs, files in os.walk(project_directory):
        for file in files:
            # 获取文件扩展名
            _, ext = os.path.splitext(file)

            # 检查是否是支持的文件类型
            if ext.lower() in supported_extensions:
                file_path = os.path.join(root, file)
                project_data["total_files"] += 1

                try:
                    print("=" * 50)
                    print(f"Processing: {file_path}")
                    result = code_parser.parse_code(file_path)
                    file_json = code_parser.print_results(result)

                    # 将文件信息添加到项目数据中
                    file_data = {
                        "file_path": file_path,
                        "file_name": file,
                        "relative_path": os.path.relpath(file_path, project_directory),
                        "file_type": ext.lower(),
                        "language": language_map.get(ext.lower(), "unknown"),
                        "analysis_result": file_json  # 假设file_json已经是字典格式
                    }

                    project_data["files"].append(file_data)
                    project_data["processed_files"] += 1

                    print(f"Successfully processed: {file_path}")
                    print()

                except Exception as e:
                    error_data = {
                        "file_path": file_path,
                        "file_name": file,
                        "relative_path": os.path.relpath(file_path, project_directory),
                        "file_type": ext.lower(),
                        "language": language_map.get(ext.lower(), "unknown"),
                        "error": str(e),
                        "status": "failed"
                    }
                    project_data["files"].append(error_data)
                    print(f"Error processing file {file_path}: {str(e)}")
                    print("Continuing with next file...\n")
                    continue

    # 保存项目级JSON到文件
    output_filename = f"{os.path.basename(project_directory)}_project_analysis.json"
    output_path = os.path.join(get_analysis_default_root_path(), output_filename)

    output_extract_filename = f"{os.path.basename(project_directory)}_project_extract_analysis.json"
    output_extract_path = os.path.join(get_analysis_default_root_path(), output_extract_filename)
    extract_value = extract_key_info(project_data)

    for fp, dt in ((output_path, project_data),
                   (output_extract_path, extract_value)):
        try:
            if os.path.exists(fp):
                os.remove(fp)
            with open(fp, 'w', encoding='utf-8') as f:
                json.dump(dt, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving JSON file {fp}: {e}")
    return extract_value



if __name__ == "__main__":

    current_directory = "."
    parser1 = parse_project(current_directory)

