#ifndef SRC_CC_PARAMS_H__
#define SRC_CC_PARAMS_H__

#include <cmath>         // nan
#include <cstdint>       // uint64_t
#include <unordered_map> // unordered_map
#include <vector>

#include "ref_callback.h"

namespace bidirectional {

/// Internal enum for directions
enum Directions {
  /// Forward
  FWD,
  /// Backward
  BWD,
  /// Both
  BOTH,
  /// No direction
  NODIR
};

/**
 * Input parameters.
 */
class Params {
 public:
  /// Direction for search
  Directions direction = bidirectional::BOTH;
  /// string with method to determine the next direction of search. Options
  /// are: unprocessed, processed and generated.
  std::string method = "unprocessed";
  /// double with time limit in seconds
  double time_limit = std::nan("na");
  /// double with threshold to stop search with total cost <= threshold
  double threshold = std::nan("na");
  /// bool with whether output path is required to be elementary
  bool elementary = false;
  /// bool with whether 2-cycles should be eliminated for non-elementary RCSPP
  bool two_cycle_elimination = false;
  /// bool with whether lower bounds based on shortest paths are used to prune
  /// labels. Experimental!
  bool bounds_pruning = false;
  /// bool with whether critical resource is found at the preprocessing stage.
  /// @see getCriticalRes. overrides critical_res value. Default false.
  bool find_critical_res = false;
  /// Resource id for the critical resource used in dominance checks and
  /// choosing the halfway point. Default is 0.
  int critical_res = 0;
  /// Callback to custom REF
  bidirectional::REFCallback* ref_callback = nullptr;

  /* Required (mandatory) visits.
   *
   * When `require_all_visits` is true, the search only accepts Source-Sink
   * paths that visit every node of the required set, and the dominance rule
   * is restricted so that a label may only dominate another label visiting
   * exactly the same required nodes. All of the members below are unused
   * (and the feature is a no-op) while `require_all_visits` is false.
   */

  /// Whether the search must only accept Source-Sink paths that visit every
  /// node in the required set. Default false (feature disabled).
  bool require_all_visits = false;
  /// Number of 64-bit words used by the required-visit bit set.
  int required_words = 0;
  /// Bit index of each required vertex in the required-visit bit set, keyed
  /// by user id. Vertices that are not required are absent from the map, so
  /// the memory used is proportional to the number of required vertices and
  /// not to the largest user id. Empty when disabled.
  std::unordered_map<int, int> required_bit_by_user_id;
  /// Bit set with every required node set (the coverage target).
  std::vector<std::uint64_t> required_mask_full;

  /* Constructors */

  Params(){};
  ~Params() {
    ref_callback = nullptr;
    delete ref_callback;
  };

  /* Public methods */

  /* Setters */
  void setDirection(const std::string& direction_in) {
    if (direction_in == "forward")
      direction = FWD;
    else if (direction_in == "backward")
      direction = BWD;
  }
  void setMethod(const std::string& method_in) { method = method_in; }
  void setTimeLimit(const double& time_limit_in) { time_limit = time_limit_in; }
  void setThreshold(const double& threshold_in) { threshold = threshold_in; }
  void setElementary(const bool& elementary_in) { elementary = elementary_in; }
  void setTwoCycleElimination(const bool& two_cycle_elimination_in) {
    two_cycle_elimination = two_cycle_elimination_in;
  };
  void setBoundsPruning(const bool& bounds_pruning_in) {
    bounds_pruning = bounds_pruning_in;
  }
  void setFindCriticalRes(const bool& find_critical_res_in) {
    find_critical_res = find_critical_res_in;
  }
  void setCriticalRes(const int& critical_res_in) {
    critical_res = critical_res_in;
  }
  /// Set callback for custom resource extensions
  void setREFCallback(bidirectional::REFCallback* cb) { ref_callback = cb; };
  /**
   * Enable the required-visit mode.
   *
   * @param[in] bit_index_by_user_id, map from the user id of each required
   * vertex to its bit index in the required-visit bit set.
   * @param[in] n_required, int with the number of required vertices (bits).
   *
   * Called by BiDirectional::setRequiredNodes, which validates the ids.
   */
  void setRequiredVisits(
      const std::unordered_map<int, int>& bit_index_by_user_id,
      const int&                          n_required) {
    require_all_visits      = true;
    required_bit_by_user_id = bit_index_by_user_id;
    required_words          = (n_required + 63) / 64;
    required_mask_full.assign(required_words, 0ULL);
    for (int b = 0; b < n_required; ++b)
      required_mask_full[b >> 6] |= (1ULL << (b & 63));
  }
};

} // namespace bidirectional

#endif // SRC_CC_PARAMS_H__
