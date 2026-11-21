export const STRUCTURE_LABEL: Record<string, string> = {
  array: "Array",
  queue: "Queue",
  stack: "Stack",
  linked_list: "Linked list",
  binary_tree: "Binary tree",
  graph_bfs: "BFS",
  graph_dfs: "DFS",
  bubble_sort: "Bubble sort",
  insertion_sort: "Insertion sort",
};

export const structureLabel = (s: string) => STRUCTURE_LABEL[s] ?? s.replace(/_/g, " ");
