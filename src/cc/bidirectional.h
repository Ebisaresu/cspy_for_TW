#ifndef SRC_CC_BIDIRECTIONAL_H__
#define SRC_CC_BIDIRECTIONAL_H__

#include <chrono>    // timing (e.g. time_point)
#include <stdexcept> // invalid_argument (setCriticalRes range check)
#include <string>    // string (termination reason)
#include <vector>

// cspy
#include "src/cc/config.h" // log-level
#include "src/cc/digraph.h"
#include "src/cc/params.h"
#include "src/cc/ref_callback.h"
#include "src/cc/search.h"

// logging
#include "spdlog/spdlog.h" // after config.h as

namespace bidirectional {

/**
 * Reason why the last call to `BiDirectional::run` stopped.
 * @see BiDirectional::getTerminationReason for the user-facing strings and
 * their exact meaning.
 */
enum class TerminationReason {
  /// `run` has not been called yet
  NOT_RUN,
  /// The search processed every generated label (ran to exhaustion) and a
  /// Source-Sink path was found. Note this is deliberately not called
  /// "optimal": exhaustion certifies optimality only when the dominance rule
  /// is sound for the resource extensions in use (for instance the
  /// `window_hard` policy is a documented exception).
  SEARCH_COMPLETED,
  /// A Source-Sink path meeting the threshold was found and the search was
  /// stopped early; that path is the one returned.
  THRESHOLD_REACHED,
  /// The time limit expired before the search could finish. A Source-Sink
  /// path found before the limit (if any) is still returned.
  TIME_LIMIT_REACHED,
  /// The search processed every generated label without finding any
  /// resource-feasible Source-Sink path.
  NO_FEASIBLE_PATH
};

/**
 * BiDirectional algorithm. see docs
 *
 * 1. ctor (memory allocation for the graph)
 * 2. add edges to graph using `addEdge`.
 * 3. [optional] set solving parameters if desired (e.g. time_limit, ...)
 * 	3.1. [optional] set callback using `setREFCallback`
 * 	3.2. [optional] set seed using `setSeed`
 * 4. call `run`
 */
class BiDirectional {
 public:
  /**
   * @param[in] number_vertices, int number of vertices in the graph (to be
   * added using addEdge)
   * @param[in] number_edges, int number of edges in the graph
   * @param[in] source_id, int vertex id for the source
   * @param[in] sink_id, int vertex id for the sink
   * @param[in] max_res, vector of double with upper bound for resource
   * consumption
   * @param[in] min_res, vector of double with lower bound for resource
   * consumption
   */
  BiDirectional(
      const int&                 number_vertices,
      const int&                 number_edges,
      const int&                 source_id,
      const int&                 sink_id,
      const std::vector<double>& max_res_in,
      const std::vector<double>& min_res_in);

  /// Default destructor
  ~BiDirectional(){};

  /* Parameters */
  /// vector with upper and lower bounds for resources
  std::vector<double> max_res;
  std::vector<double> min_res;
  int                 source_id;
  int                 sink_id;

  /* Methods */

  /* Graph creation */
  /// Wrapper to add nodes to the graph. @see DiGraph::addNodes
  void addNodes(const std::vector<int>& nodes) { graph_ptr_->addNodes(nodes); }
  /// Add an edge to the graph
  void addEdge(
      const int&                 tail,
      const int&                 head,
      const double&              weight,
      const std::vector<double>& resource_consumption) {
    graph_ptr_->addEdge(tail, head, weight, resource_consumption);
  }
  /// run the algorithm (assumes all the appropriate options are set)
  void run();

  /* Getters */

  /// Return the final path
  std::vector<int> getPath() const;
  /// Return the consumed resources
  std::vector<double> getConsumedResources() const;
  /// Return the total cost
  double getTotalCost() const;
  /**
   * Return the reason why the last call to `run` stopped, as a string:
   *   - "not_run": `run` has not been called yet.
   *   - "completed": the search processed every generated label and a
   *     Source-Sink path was found. This certifies optimality only when the
   *     dominance rule is sound for the resource extensions in use.
   *   - "threshold_reached": a Source-Sink path meeting the threshold was
   *     found and the search stopped early; that path is the one returned.
   *   - "time_limit_reached": the time limit expired before the search could
   *     finish. A Source-Sink path found before the limit (if any) is still
   *     returned; otherwise the result is degenerate and the instance status
   *     is unknown (not proven infeasible).
   *   - "no_feasible_path": the search processed every generated label
   *     without finding any resource-feasible Source-Sink path.
   *
   * Two caveats:
   *   - `run` is single-shot per object: the search containers are not reset
   *     between calls, so a second call to `run` on the same object throws
   *     std::runtime_error. Build a fresh object for every run.
   *   - The time limit is checked before the threshold, so when both stop
   *     conditions hold at the same iteration the reason is
   *     "time_limit_reached". For the same reason a search whose last
   *     iteration coincides with the time limit expiring may report
   *     "time_limit_reached" instead of "completed" (conservative: it never
   *     overstates how far the search got).
   */
  std::string getTerminationReason() const;
  /// After running the algorithm, one can check if critical resource is tight
  /// (difference between final resource and maximum) and prints a message if it
  /// doesn't match to the one chosen in Params.
  void checkCriticalRes() const;
  /**
   * Throw std::runtime_error if `run` has not been called yet.
   *
   * The result getters read `best_label_`, which stays null until `init`
   * allocates it. @param[in] getter, name used in the message.
   */
  void checkHasRun(const char* getter) const;

  /* Setters: wrappers. @see bidirectional::Params */

  /// @see bidirectional::Params
  void setDirection(const std::string& direction_in) {
    params_ptr_->setDirection(direction_in);
  };
  /// @see bidirectional::Params
  void setMethod(const std::string& method_in) {
    params_ptr_->setMethod(method_in);
  }
  /// @see bidirectional::Params
  void setTimeLimit(const double& time_limit_in) {
    params_ptr_->setTimeLimit(time_limit_in);
  }
  /// @see bidirectional::Params
  void setThreshold(const double& threshold_in) {
    params_ptr_->setThreshold(threshold_in);
  }
  /// @see bidirectional::Params
  void setThresholdStrict(const bool& threshold_strict_in) {
    params_ptr_->setThresholdStrict(threshold_strict_in);
  }
  /// @see bidirectional::Params
  void setElementary(const bool& elementary_in) {
    params_ptr_->setElementary(elementary_in);
  }
  /// @see bidirectional::Params
  void setTwoCycleElimination(const bool& two_cycle_elimination_in) {
    params_ptr_->setTwoCycleElimination(two_cycle_elimination_in);
  }
  /// @see bidirectional::Params
  void setBoundsPruning(const bool& bounds_pruning_in) {
    params_ptr_->setBoundsPruning(bounds_pruning_in);
  }
  /// @see bidirectional::Params and getCriticalRes
  void setFindCriticalRes(const bool& find_critical_res_in) {
    params_ptr_->setFindCriticalRes(find_critical_res_in);
  }
  /**
   * @see bidirectional::Params
   *
   * The index is validated here rather than trusted: `critical_res` is used
   * unchecked to subscript `max_res`, `min_res` and every label's resource
   * vector all over the search, so an out-of-range value corrupts memory
   * instead of producing a wrong answer.
   */
  void setCriticalRes(const int& critical_res_in) {
    if (critical_res_in < 0 ||
        critical_res_in >= static_cast<int>(max_res.size())) {
      throw std::invalid_argument(
          "[BiDirectional] critical_res = " + std::to_string(critical_res_in) +
          " is out of range; it must be an index into max_res, i.e. in [0, " +
          std::to_string(max_res.size()) + ")");
    }
    params_ptr_->setCriticalRes(critical_res_in);
  }
  /// Pass python callback for label extensions.
  /// Note: swig needs namespace specifier
  void setREFCallback(bidirectional::REFCallback* cb) {
    params_ptr_->setREFCallback(cb);
  }
  /**
   * Restrict the search to Source-Sink paths that visit every node in
   * `required_user_ids` (the mandatory-visit mode, e.g. for the Traveling
   * Salesman Problem with Time Windows).
   *
   * Must be called after `addNodes`. Requires `elementary = true` and
   * `direction = forward`; both are checked in `run`.
   *
   * @param[in] required_user_ids, vector of int with the user ids of the
   * vertices that every accepted path must visit. Duplicates are ignored.
   * Must not be empty: an empty required set would silently make the whole
   * mandatory-visit mode vacuous, so it is rejected.
   */
  void setRequiredNodes(const std::vector<int>& required_user_ids);
  /// set random using a given seed
  // void setSeed(const int& seed) { std::srand(seed); }

 private:
  /// Search options for the algorithm. @see bidirectional::Params
  std::unique_ptr<Params> params_ptr_;
  /// Pointer to graph
  std::unique_ptr<DiGraph> graph_ptr_;
  /// Start time to ensure time limit is met
  std::chrono::time_point<std::chrono::system_clock> start_time_;
  /// Current primal bound for a complete source-sink path
  double primal_st_bound_ = std::nan("nan");
  /// iteration number
  int iteration_ = 0;
  // whether the search terminated early with a valid source-sink path
  bool       terminated_early_w_st_path_ = false;
  Directions terminated_early_w_st_path_direction_;
  /// Why the last call to `run` stopped. Written only (never read) during the
  /// search, so recording it cannot influence any search decision.
  /// @see getTerminationReason
  TerminationReason termination_reason_ = TerminationReason::NOT_RUN;

  /// Vectors with current maximum and minimum resources (first entry contains
  /// the dynamic halfway point).
  std::vector<double> max_res_curr_, min_res_curr_;

  /* labels and containers */

  /// Final best label (merged or otherwise)
  std::shared_ptr<labelling::Label> best_label_;

  std::unique_ptr<Search> fwd_search_ptr_, bwd_search_ptr_;

  /* Initialisation Methods */

  /// Wrapper to initialise search in the appropriate direction
  void init();
  /// Initialise respective Search
  void initSearch(const Directions& direction);
  /// Initialise labels with appropriate resources
  void initResourceBounds();
  /// Make `unprocessed_labels_` a heap
  void initContainers();
  /// Construct first label and initialise `unprocessed_labels_` heap,
  /// `best_labels` source bucket and `visited_vertices`.
  void initLabels(const Directions& direction);
  /**
   * Run preprocessing steps if required. Currently includes:
   *   - Obtain shortest paths bounds
   *   - TODO: Bounding and adjusting of resource bounds
   */
  void runPreprocessing();

  /* Search Methods */
  /// Get the next direction to search
  Directions getDirection() const;

  Search* getSearchPtr(Directions direction) {
    if (direction == FWD)
      return fwd_search_ptr_.get();
    return bwd_search_ptr_.get();
  };

  /// Advance the search in a given direction
  void move(const Directions& direction);

  /// checks if the time_limit if over (if set) or if a label under the
  /// threshold has been found (if set). Sets terminated_early_w_st_path_
  bool terminate(const Directions& direction, const labelling::Label& label);
  /// @overload to just use current intermediate_label in direction
  bool terminate(const Directions& direction);

  /* checks */

  /// Wrapper to check whether a label is valid. Checks s-t path + threshold.
  bool checkValidLabel(
      const Directions&       direction,
      const labelling::Label& label);

  /// Returns true if half-way points are being violated. False otherwise
  bool checkBounds(const Directions& direction);

  /**
   * If bounds_pruning is true then check whether an input label plus a lower
   * bound for the path (from the node of the label to the source/sink)
   * violates the current primal bound.
   *
   * @return true if primal bound is violated, false otherwise.
   * i.e. if true, then input label cannot appear in the optimal solution.
   */
  bool checkPrimalBound(
      const Directions&       direction,
      const labelling::Label& candidate_label);

  /**
   * checks if a given vertex has been visited in a given direction
   *
   * @param[in] direction, Directions
   * @param[in] vertex_idx, int. Lemon id of vertex to check.
   * @return true if it has been visited false otherwise
   */
  bool checkVertexVisited(const Directions& direction, const int& vertex_idx);

  /// Call labelling::getNextLabel to get next label in the heap
  /// (unprocessed_labels_) and update the current_label member
  void updateCurrentLabel(const Directions& direction);

  /// Update half-way points and check if the current labels violates them, in
  /// which case sets the stop member to true.
  void updateHalfWayPoints(const Directions& direction);

  /**
   * Given a candidate_label by looking at the vector of labels (bucket) for
   * that node, we can check if the candidate_label has already been saved or
   * it is dominated. If both of these conditions are false, not seen and not
   * dominated, then we add it to the bucket.
   * Additionally, if the bounds_pruning option is active, we check the bounds
   * here, as an extra condition to add a label to the bucket.
   * Also, `visited_vertices` is updated here.
   */
  void updateEfficientLabels(
      const Directions&       direction,
      const labelling::Label& candidate_label);

  /// Update `best_labels` entry by node with the candidate_label if
  /// appropriate
  void updateBestLabels(
      const Directions&       direction,
      const labelling::Label& candidate_label);

  /**
   * Iterate over the neighbours for the current label node and extends it
   * when appropriate.
   */
  void extendCurrentLabel(const Directions& direction);

  /// Helper function to extend along a given arc
  void extendSingleLabel(
      labelling::Label* label,
      const Directions& direction,
      const AdjVertex&  adj_vertex);

  /**
   * Saves/updates globally best label and check if it is Source-Sink so we
   * can use it in the bounding. Sets `final_label`
   */
  void saveCurrentBestLabel(const Directions& direction);

  /* Post processing */

  /**
   * Wrapper to process of output path.
   * Either saves appropriate label (single-direction search or early
   * termination)
   * or, calls joinLabels to merge forward + backward labels
   */
  void postProcessing();

  /**
   * get upper bound using a valid source-sink path (minimum of both forward
   * and backward source-sink paths)
   * @return double with upper bound
   */
  double getUB();

  /**
   * get minimum weight across all forward / backward labels
   *
   * @param[out] fwd_min, double, minimum across all forward labels
   * @param[out] bwd_min, double, minimum across all backward labels
   */
  void getMinimumWeights(double* fwd_min, double* bwd_min);

  /// return time since start time in seconds.

  double getElapsedTime() {
    std::chrono::duration<double> duration =
        (std::chrono::system_clock::now() - start_time_);
    return static_cast<double>(duration.count());
  }

  /**
   * Turn the provisional termination reason into the final one, after
   * `postProcessing` has decided `best_label_`. A search that ran to
   * exhaustion (provisionally SEARCH_COMPLETED) without producing any
   * Source-Sink path becomes NO_FEASIBLE_PATH; every other reason is kept.
   */
  void finalizeTerminationReason();

  /**
   * The procedure "Join" or Algorithm 3 from Righini and Salani (2006).
   *
   * @see: https://www.sciencedirect.com/science/article/pii/S1572528606000417
   */
  void joinLabels();
};

} // namespace bidirectional

#endif // SRC_CC_BIDIRECTIONAL_H__
