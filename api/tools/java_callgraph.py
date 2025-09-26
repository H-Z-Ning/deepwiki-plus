import os
import json
import javalang
from javalang.tree import MethodInvocation, MethodDeclaration
import networkx as nx
from collections import defaultdict
import argparse
from pathlib import Path


class JavaCallChainAnalyzer:
    def __init__(self, project_path):
        self.project_path = project_path
        self.call_graph = nx.DiGraph()
        self.methods_info = {}
        self.class_methods = defaultdict(dict)

    def parse_java_file(self, file_path):
        """解析单个Java文件，提取方法定义和调用关系"""
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                content = file.read()

            tree = javalang.parse.parse(content)

            # 提取包名和类名
            package_name = tree.package.name if tree.package else "default"
            class_name = None

            for path, node in tree:
                if isinstance(node, javalang.tree.ClassDeclaration):
                    class_name = node.name
                    full_class_name = f"{package_name}.{class_name}"
                    break

            if not class_name:
                return

            # 将绝对路径转换为相对于项目路径的相对路径
            relative_file_path = os.path.relpath(file_path, self.project_path)

            # 分析方法和调用
            self.analyze_methods_and_calls(tree, full_class_name, relative_file_path)

        except Exception as e:
            print(f"解析文件 {file_path} 时出错: {e}")

    def analyze_methods_and_calls(self, tree, class_name, file_path):
        """分析类中的方法和调用关系"""
        current_method = None

        for path, node in tree:
            # 处理方法声明
            if isinstance(node, MethodDeclaration):
                method_name = node.name
                parameters = [param.type.name for param in node.parameters]
                param_str = ", ".join(parameters) if parameters else ""
                # 简化方法名，只保留类名和方法名
                simplified_method_name = f"{class_name.split('.')[-1]}.{method_name}({param_str})"

                current_method = simplified_method_name

                # 添加到图中，同时存储方法信息作为节点属性
                self.call_graph.add_node(simplified_method_name,
                                         class_name=class_name,
                                         method_name=method_name,
                                         file_path=file_path,
                                         parameters=parameters)

                # 记录类的方法
                self.class_methods[class_name][method_name] = simplified_method_name

            # 处理方法调用
            elif isinstance(node, MethodInvocation) and current_method:
                self.process_method_invocation(node, current_method, class_name)

    def process_method_invocation(self, invocation, caller_method, current_class):
        """处理方法调用，建立调用关系"""
        try:
            method_name = invocation.member

            # 确定被调用方法的完整名称
            callee_method = self.resolve_callee_method(invocation, method_name, current_class)

            if callee_method:
                # 添加调用关系
                self.call_graph.add_edge(caller_method, callee_method)

        except Exception as e:
            print(f"处理方法调用时出错: {e}")

    def resolve_callee_method(self, invocation, method_name, current_class):
        """解析被调用方法的完整名称"""
        # 简单的解析逻辑，实际项目中可能需要更复杂的类型推断
        if invocation.qualifier:
            # 有限定符的方法调用，如 object.method()
            qualifier = invocation.qualifier
            # 简化方法名
            callee_method = f"{qualifier.split('.')[-1]}.{method_name}()"
            # 为外部方法添加基本节点信息
            if callee_method not in self.call_graph:
                self.call_graph.add_node(callee_method, file_path="external")
            return callee_method
        else:
            # 没有限定符，可能是当前类的方法或导入类的方法
            # 首先检查是否是当前类的方法
            if method_name in self.class_methods[current_class]:
                return self.class_methods[current_class][method_name]
            else:
                # 简化处理，返回方法名
                callee_method = f"unknown.{method_name}()"
                # 为未知方法添加基本节点信息
                if callee_method not in self.call_graph:
                    self.call_graph.add_node(callee_method, file_path="unknown")
                return callee_method

    def find_all_java_files(self):
        """查找项目中的所有Java文件"""
        java_files = []
        for root, dirs, files in os.walk(self.project_path):
            for file in files:
                if file.endswith('.java'):
                    full_path = os.path.join(root, file)
                    java_files.append(full_path)
        return java_files

    def analyze_project(self):
        """分析整个Java项目"""
        print("开始分析Java项目...")
        java_files = self.find_all_java_files()
        print(f"找到 {len(java_files)} 个Java文件")

        for i, java_file in enumerate(java_files, 1):
            print(f"分析文件 {i}/{len(java_files)}: {java_file}")
            self.parse_java_file(java_file)

        print(f"分析完成！共找到 {len(self.call_graph.nodes)} 个方法，{len(self.call_graph.edges)} 个调用关系")

    def save_call_chain(self, output_file_path):
        """保存调用链信息到本地JSON文件"""
        # 提取目录路径并创建目录
        output_dir = os.path.dirname(output_file_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        # 检查是否有有效的节点或边
        if len(self.call_graph.nodes) == 0 and len(self.call_graph.edges) == 0:
            print("没有找到任何方法或调用关系，不生成call_chain.json文件")
            return

        # 根据Java文件路径对节点进行聚合
        file_nodes = defaultdict(list)

        # 遍历所有节点，按文件路径分类
        for node in self.call_graph.nodes:
            # 获取节点的文件路径属性
            node_attrs = self.call_graph.nodes[node]
            file_path = node_attrs.get('file_path', 'unknown')

            # 将节点添加到对应的文件分组中
            file_nodes[file_path].append(node)

        # 构建聚合后的数据结构
        call_data = {
            'nodes_by_file': dict(file_nodes),  # 按文件路径聚合的节点
            'edges': list(self.call_graph.edges)
        }

        # 检查nodes_by_file和edges是否为空
        has_nodes = any(len(nodes) > 0 for nodes in call_data['nodes_by_file'].values())
        has_edges = len(call_data['edges']) > 0

        if not has_nodes and not has_edges:
            print("nodes_by_file和edges都为空，不生成call_chain.json文件")
            return

        # 保存JSON文件到指定路径
        with open(output_file_path, 'w', encoding='utf-8') as f:
            json.dump(call_data, f, indent=2, ensure_ascii=False)

        print(f"调用链信息已保存到 {output_file_path}")

    def find_call_chains(self, start_method, end_method, max_depth=10):
        """查找两个方法之间的调用链"""
        try:
            chains = list(nx.all_simple_paths(self.call_graph, start_method, end_method, cutoff=max_depth))
            return chains
        except nx.NetworkXNoPath:
            return []
        except nx.NodeNotFound:
            print(f"方法不存在: {start_method} 或 {end_method}")
            return []

    def get_method_callers(self, method_name):
        """获取调用指定方法的所有方法"""
        if method_name not in self.call_graph:
            return []
        return list(self.call_graph.predecessors(method_name))

    def get_method_callees(self, method_name):
        """获取指定方法调用的所有方法"""
        if method_name not in self.call_graph:
            return []
        return list(self.call_graph.successors(method_name))


def analyze_java_callgraph(project_path: str, output_file_path: str = 'output') -> None:
    """
    真正的分析逻辑，接收普通参数，方便被其他模块直接调用。
    """
    if not os.path.exists(project_path):
        print(f"错误: 项目路径 {project_path} 不存在")
        return

    # 创建分析器并分析项目
    analyzer = JavaCallChainAnalyzer(project_path)
    analyzer.analyze_project()
    analyzer.save_call_chain(output_file_path)

    # 示例：查找特定调用链
    print("\n示例调用链分析:")
    methods = list(analyzer.call_graph.nodes)
    if len(methods) >= 2:
        start_method = methods[0]
        end_method = methods[-1] if len(methods) > 1 else methods[0]

        chains: List[List[str]] = analyzer.find_call_chains(
            start_method, end_method, max_depth=3)
        if chains:
            print(f"\n找到从 {start_method} 到 {end_method} 的调用链:")
            for i, chain in enumerate(chains[:3]):  # 只显示前3条
                print(f"链 {i + 1}: {' -> '.join(chain)}")
        else:
            print(f"未找到从 {start_method} 到 {end_method} 的调用链")


def main() -> None:
    """命令行入口，仅负责解析参数，然后调用 analyze()。"""
    parser = argparse.ArgumentParser(description='Java项目调用链分析工具')
    parser.add_argument('project_path', help='Java项目路径')
    parser.add_argument('-o', '--output', default='output', help='输出目录')
    args = parser.parse_args()

    # 把解析到的参数传进去
    analyze_java_callgraph(args.project_path, args.output)


if __name__ == '__main__':
    main()