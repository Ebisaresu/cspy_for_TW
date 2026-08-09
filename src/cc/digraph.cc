#include "digraph.h"

#include <algorithm> // find_if, all_of
#include <stdexcept> // invalid_argument
#include <string>    // to_string

namespace bidirectional {

DiGraph::DiGraph(
    const int& num_nodes_in,
    const int& num_arcs_in,
    const int& source_id_in,
    const int& sink_id_in)
    // Listed in declaration order, which is the order they are actually
    // initialised in: weight_map_ptr and res_map_ptr dereference
    // lemon_graph_ptr, so reading this list as if it were the running order
    // would suggest a use of a not-yet-constructed member that is not there.
    : number_vertices(num_nodes_in),
      number_edges(num_arcs_in),
      lemon_graph_ptr(std::make_unique<LemonGraph>()),
      weight_map_ptr(
          std::make_unique<LemonGraph::ArcMap<double>>(*lemon_graph_ptr)),
      res_map_ptr(std::make_unique<LemonGraph::ArcMap<std::vector<double>>>(
          *lemon_graph_ptr)),
      negative_cost_cycle_present(NegativeCostCyclePresent::ABSENT),
      source_id_(source_id_in),
      sink_id_(sink_id_in) {
  lemon_graph_ptr->reserveNode(num_nodes_in);
  lemon_graph_ptr->reserveArc(num_arcs_in);
  vertices.resize(num_nodes_in);
}

void DiGraph::addNodes(const std::vector<int>& user_nodes) {
  // `vertices` was sized once, by the constructor, from the node count the
  // caller declared. Writing `vertices[count]` below for more nodes than that
  // is a buffer overflow, so the two have to be reconciled here rather than
  // trusted to agree.
  if (static_cast<int>(user_nodes.size()) > number_vertices) {
    throw std::invalid_argument(
        "[DiGraph] addNodes was given " + std::to_string(user_nodes.size()) +
        " nodes, but the graph was constructed for " +
        std::to_string(number_vertices));
  }
  int  count        = 0;
  bool source_saved = false, sink_saved = false;
  for (const int& user_node : user_nodes) {
    lemon_graph_ptr->addNode();
    // Create and save vertex (lemon id is just count)
    const Vertex new_vertex = {count, user_node};
    vertices[count]         = new_vertex;
    // Save source/sink
    if (!source_saved && user_node == source_id_) {
      source       = new_vertex;
      source_saved = true;
    } else if (!sink_saved && user_node == sink_id_) {
      sink       = new_vertex;
      sink_saved = true;
    }
    ++count;
  }
  // The search reads source.lemon_id / sink.lemon_id unconditionally. If
  // neither node carried the declared id they are still {-1, -1}, which LEMON
  // would turn into an out-of-range node access.
  if (!source_saved || !sink_saved) {
    throw std::invalid_argument(
        "[DiGraph] addNodes did not receive the " +
        std::string(!source_saved ? "source" : "sink") + " node (user id " +
        std::to_string(!source_saved ? source_id_ : sink_id_) + ")");
  }
}

void DiGraph::addEdge(
    const int&                 tail,
    const int&                 head,
    const double&              weight,
    const std::vector<double>& resource_consumption) {
  // Get vertices
  const LemonNode& tail_lnode = getLNodeFromUserId(tail);
  const LemonNode& head_lnode = getLNodeFromUserId(head);
  const LemonArc&  arc        = lemon_graph_ptr->addArc(tail_lnode, head_lnode);
  (*weight_map_ptr)[arc]      = weight;
  (*res_map_ptr)[arc]         = resource_consumption;
  if (weight < 0)
    negative_cost_cycle_present = NegativeCostCyclePresent::UNKNOWN;
  // The flag is a property of the whole graph, so it accumulates: assigning
  // it here would let the last edge added decide it on its own, and one edge
  // with a negative resource would go unnoticed as soon as any edge was added
  // after it.
  all_resources_positive =
      all_resources_positive && std::all_of(
                                    resource_consumption.cbegin(),
                                    resource_consumption.cend(),
                                    [](const double& v) { return (v >= 0); });
}

AdjVertex DiGraph::getAdjVertex(const LemonArc& arc, const bool& forward)
    const {
  LemonNode node;
  if (forward) {
    node = head(arc);
  } else {
    node = tail(arc);
  }
  const Vertex&              vertex               = getVertexFromLNode(node);
  const double&              weight               = getWeight(arc);
  const std::vector<double>& resource_consumption = getRes(arc);
  return AdjVertex(vertex, weight, resource_consumption);
}

/// For conversion between user node labels and LemonGraph internal
int DiGraph::getNodeIdFromUserId(const int& user_id) const {
  auto it = std::find_if(
      vertices.begin(), vertices.end(), [&user_id](const Vertex& v) {
        return (v.user_id == user_id);
      });
  // Without this the miss returns `vertices.end()->lemon_id`, which reads past
  // the end of the vector and then feeds the garbage it finds to
  // lemon::SmartDigraph::nodeFromId -- an out-of-bounds index into LEMON's
  // node array, i.e. a crash rather than an error message.
  if (it == vertices.end()) {
    throw std::invalid_argument(
        "[DiGraph] node " + std::to_string(user_id) +
        " is not in the graph (addEdge before addNodes, or an edge referring"
        " to a node that was never added)");
  }
  return it->lemon_id;
}

} // namespace bidirectional
