#ifndef SRC_CC_SEARCH_H__
#define SRC_CC_SEARCH_H__

#include <cstdint>       // uint64_t (efficient label group keys)
#include <memory>        // unique_ptr
#include <set>
#include <unordered_map> // efficient labels grouped by mask key
#include <vector>

#include "labelling.h"

namespace bidirectional {

class Search {
 public:
  /// Direction of Search
  Directions direction;
  //  Params     params;
  /// Stopping criteria for each direction
  bool stop = false;
  /// Stopping criteria for each direction
  bool bound_exceeded = false;
  /// Number of unprocessed labels generated
  int unprocessed_count = 0;
  /// Number of labels processed
  int processed_count = 0;
  /// Number of labels generated (includes the possibly infeasible extensions)
  int generated_count = 0;

  /* Search-related parameters */

  /// Lower bounds from any node to sink
  std::unique_ptr<std::vector<double>> lower_bound_weight;
  /// vector with indices of vertices visited
  std::set<int>                     visited_vertices;
  std::shared_ptr<labelling::Label> current_label;
  /// Intermediate current best label with possibly complete source-sink path
  /// (shared pointer as we want to be able to substitute it without
  /// resetting)
  std::shared_ptr<labelling::Label> intermediate_label;

  /**
   * Pareto-optimal labels per node, grouped by a key derived from the
   * required-visit mask (the mask's first word; 0 whenever the
   * mandatory-visit mode is off, so everything lands in one group and the
   * behaviour is exactly the flat vector this used to be).
   *
   * The grouping exists because dominance under `require_all_visits` only
   * relates labels with equal masks: comparing a candidate against every
   * label at the vertex is quadratic in the label count, and almost every
   * pair in a TSPTW instance fails the mask test. Grouping turns those
   * non-pairs into pairs never visited. Masks longer than one word may share
   * a group (the key is only the first word); that is harmless, because
   * checkDominance re-checks the full mask.
   */
  std::vector<
      std::unordered_map<std::uint64_t, std::vector<labelling::Label>>>
      efficient_labels;
  /**
   * Number of labels held in `efficient_labels` per node, across all groups.
   * Kept because updateEfficientLabels decides whether to run the dominance
   * pass on the total held at the vertex (its pre-existing behaviour), which
   * the grouped container no longer answers in O(1).
   */
  std::vector<int> efficient_label_counts;
  /// vector with pointer to label with least weight (per node) in each
  /// direction
  std::vector<std::shared_ptr<labelling::Label>> best_labels;
  /**
   * heap vector to keep unprocessed labels ordered.
   * the order depends on the on the direction of the search.
   * i.e. forward -> increasing in the monotone resource,
   * backward -> decreasing in the monotone resource.
   */
  std::unique_ptr<std::vector<labelling::Label>> unprocessed_labels;

  // TODO: Use bucket-heap
  /* Heap operations for vector of labels */

  /**
   * Initialises heap using the appropriate comparison
   * i.e. increasing in the monotone resource forward lists, decreasing
   * otherwise
   */
  void makeHeap();

  /**
   * Push new elements in heap using the appropriate comparison
   * i.e. increasing in the monotone resource forward lists, decreasing
   * otherwise
   */
  void pushHeap();

  void pushUnprocessedLabel(const labelling::Label& label) {
    unprocessed_labels->push_back(label);
    pushHeap();
  }

  /// Group key of a label: first word of the required-visit mask (0 when the
  /// mandatory-visit mode is off or the mask is empty).
  static std::uint64_t efficientLabelKey(const labelling::Label& label) {
    return label.required_visited_mask.words()[0];
  }

  void pushEfficientLabel(const int& lemon_id, const labelling::Label& label) {
    efficient_labels[lemon_id][efficientLabelKey(label)].push_back(label);
    ++efficient_label_counts[lemon_id];
  }

  /// Replace best label
  void replaceBestLabel(const int& lemon_id, const labelling::Label& label) {
    auto label_ptr = std::make_shared<labelling::Label>(label);
    best_labels[lemon_id].swap(label_ptr);
  }

  /// Replace best label
  void replaceCurrentLabel(const labelling::Label& label) {
    auto label_ptr = std::make_shared<labelling::Label>(label);
    current_label.swap(label_ptr);
  }

  /// Replace intermediate label
  void replaceIntermediateLabel(const labelling::Label& label) {
    auto label_ptr = std::make_shared<labelling::Label>(label);
    intermediate_label.swap(label_ptr);
  }

  /// Update vertices visited
  void addVisitedVertex(const int& lemon_id) {
    visited_vertices.insert(lemon_id);
  }

  Search(const Directions& direction_in);
  ~Search(){};
};

} // namespace bidirectional

#endif // SRC_CC_SEARCH_H__
