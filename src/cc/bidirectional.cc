#include "src/cc/bidirectional.h"

#include <algorithm>     // sort, all_of, find, min, max
#include <limits>        // numeric_limits
#include <stdexcept>     // invalid_argument, runtime_error
#include <string>        // to_string
#include <unordered_map> // unordered_map
#include <unordered_set> // unordered_set

#include "src/cc/preprocessing.h" // lowerBoundWeight, getCriticalRes

namespace bidirectional {

/* Public methods */

BiDirectional::BiDirectional(
    const int&                 number_vertices,
    const int&                 number_edges,
    const int&                 source_id,
    const int&                 sink_id,
    const std::vector<double>& max_res_in,
    const std::vector<double>& min_res_in)
    : max_res(max_res_in),
      min_res(min_res_in),
      // Private pointer initialisations
      params_ptr_(std::make_unique<bidirectional::Params>()),
      graph_ptr_(std::make_unique<DiGraph>(
          number_vertices,
          number_edges,
          source_id,
          sink_id)),
      fwd_search_ptr_(std::make_unique<bidirectional::Search>(FWD)),
      bwd_search_ptr_(std::make_unique<bidirectional::Search>(BWD)) {
  // The search indexes both bounds by the critical resource, which defaults
  // to 0, so a problem with no resources is an out-of-bounds read on the very
  // first label. Mismatched lengths are the same thing one resource further
  // along: the feasibility loop is bounded by the label's resource vector and
  // reads whichever bound is shorter past its end.
  if (max_res_in.empty()) {
    throw std::invalid_argument(
        "[BiDirectional] max_res and min_res must have at least one entry"
        " (the critical resource)");
  }
  if (max_res_in.size() != min_res_in.size()) {
    throw std::invalid_argument(
        "[BiDirectional] max_res and min_res must have the same length; got " +
        std::to_string(max_res_in.size()) + " and " +
        std::to_string(min_res_in.size()));
  }
#if SPDLOG_ACTIVE_LEVEL == SPDLOG_LEVEL_DEBUG
  // Needed as not printed otherwise
  spdlog::set_level(spdlog::level::debug);
#endif
  spdlog::default_logger()->set_pattern("%v");
  SPDLOG_INFO(
      "************************************************************************"
      "********");
  // spdlog::set_pattern("%+"); // back to default format
}

/**
 * `best_label_` is only allocated by `init`, which `run` calls. Every result
 * getter below therefore has to cope with being called first: dereferencing
 * the null shared pointer is undefined behaviour, and in practice it takes
 * the whole process down. Inside a Jupyter kernel that surfaces as "the
 * kernel appears to have died" with no Python traceback at all, which tells
 * the user nothing about what they did wrong.
 */
void BiDirectional::checkHasRun(const char* getter) const {
  if (!best_label_) {
    throw std::runtime_error(
        std::string("[BiDirectional] ") + getter +
        " was called before run(). Call run() first; there is no result to"
        " report yet.");
  }
}

std::vector<int> BiDirectional::getPath() const {
  checkHasRun("getPath");
  return best_label_->partial_path;
}

std::vector<double> BiDirectional::getConsumedResources() const {
  checkHasRun("getConsumedResources");
  return best_label_->resource_consumption;
}

double BiDirectional::getTotalCost() const {
  checkHasRun("getTotalCost");
  return best_label_->weight;
}

std::string BiDirectional::getTerminationReason() const {
  switch (termination_reason_) {
    case TerminationReason::SEARCH_COMPLETED:
      return "completed";
    case TerminationReason::THRESHOLD_REACHED:
      return "threshold_reached";
    case TerminationReason::TIME_LIMIT_REACHED:
      return "time_limit_reached";
    case TerminationReason::NO_FEASIBLE_PATH:
      return "no_feasible_path";
    case TerminationReason::NOT_RUN:
    default:
      return "not_run";
  }
}

void BiDirectional::checkCriticalRes() const {
  checkHasRun("checkCriticalRes");
  const std::vector<double>& res      = best_label_->resource_consumption;
  double                     min_diff = std::numeric_limits<double>::infinity();
  int                        min_r    = 0;
  // `res` comes from a label, whose length is whatever the resource extension
  // produced; `max_res` is the user's. They agree for the built-in additive
  // REFs, but a custom REF_callback returning a longer vector would otherwise
  // walk off the end of `max_res` here.
  const int n = static_cast<int>(std::min(res.size(), max_res.size()));
  for (int r = 0; r < n; r++) {
    const double& diff = max_res[r] - res[r];
    if (diff < min_diff) {
      min_diff = diff;
      min_r    = r;
    }
  }
  if (min_r != params_ptr_->critical_res)
    SPDLOG_WARN(
        "Critical resource {} does not match final tighest {}",
        params_ptr_->critical_res,
        min_r);
}

void BiDirectional::setRequiredNodes(
    const std::vector<int>& required_user_ids) {
  // `vertices` is pre-sized by the DiGraph constructor, so its size says
  // nothing about whether the nodes have been added; the LEMON graph node
  // count does.
  if (graph_ptr_->vertices.empty() ||
      graph_ptr_->lemon_graph_ptr->nodeNum() == 0) {
    throw std::invalid_argument(
        "[BiDirectional] setRequiredNodes must be called after addNodes");
  }
  // Only the first `n_added` entries of `vertices` have been filled in by
  // addNodes; the remaining ones are still value-initialised.
  const int n_added = std::min(
      static_cast<int>(graph_ptr_->vertices.size()),
      graph_ptr_->lemon_graph_ptr->nodeNum());
  if (required_user_ids.empty()) {
    throw std::invalid_argument(
        "[BiDirectional] setRequiredNodes was given an empty set of required"
        " nodes; the requirement would be vacuous. Do not call it at all to"
        " keep the mandatory-visit mode disabled");
  }
  // Both containers below are sized by the number of vertices / required
  // nodes and not by the largest user id, so that sparse user ids (for
  // instance {0, 1, 100000000}) cost no extra memory.
  std::unordered_set<int> vertex_ids;
  vertex_ids.reserve(n_added);
  for (int i = 0; i < n_added; ++i) {
    if (graph_ptr_->vertices[i].user_id < 0) {
      throw std::invalid_argument(
          "[BiDirectional] setRequiredNodes requires non-negative user ids");
    }
    vertex_ids.insert(graph_ptr_->vertices[i].user_id);
  }

  std::unordered_map<int, int> bit_index;
  bit_index.reserve(required_user_ids.size());
  int bit = 0;
  for (const int& id : required_user_ids) {
    if (vertex_ids.count(id) == 0) {
      throw std::invalid_argument(
          "[BiDirectional] required node " + std::to_string(id) +
          " is not a vertex of the graph");
    }
    if (id == graph_ptr_->source.user_id || id == graph_ptr_->sink.user_id) {
      throw std::invalid_argument(
          "[BiDirectional] the source and the sink cannot be required nodes");
    }
    if (bit_index.count(id) > 0)
      continue; // duplicates ignored
    bit_index[id] = bit++;
  }
  params_ptr_->setRequiredVisits(bit_index, bit);
}

void BiDirectional::run() {
  // `run` is single-shot per object: `init` does not rebuild the search
  // containers, so a second call walks the leftovers of the first. That was
  // documented as "returns a degenerate result", but it is worse than that --
  // with direction = backward the joining step reaches processBwdLabel with a
  // default-constructed label, whose params_ptr is null and whose resource
  // vector is empty, and the process dies. Re-executing a notebook cell is
  // enough to hit it, so refuse the second call and say what to do instead.
  if (termination_reason_ != TerminationReason::NOT_RUN) {
    throw std::runtime_error(
        "[BiDirectional] run() has already been called on this object. The"
        " search state is not rebuilt between calls; construct a new"
        " BiDirectional for every run.");
  }
  if (params_ptr_->require_all_visits) {
    if (params_ptr_->direction != FWD) {
      throw std::invalid_argument(
          "[BiDirectional] required nodes are only supported with direction ="
          " forward");
    }
    if (!params_ptr_->elementary) {
      throw std::invalid_argument(
          "[BiDirectional] required nodes require elementary = true");
    }
  }
  start_time_ = std::chrono::system_clock::now();
  // Reset the early-termination state from any previous call to `run`, so a
  // stale flag cannot leak into this run's post-processing. Note `run` is
  // still single-shot per object: the search containers are not rebuilt, so
  // a second call returns a degenerate result (see getTerminationReason).
  terminated_early_w_st_path_ = false;
  // Provisional reason: exhaustion. Overwritten by `terminate` (time limit)
  // or `checkValidLabel` (threshold) when they stop the search early, and
  // turned into NO_FEASIBLE_PATH by `finalizeTerminationReason` when the
  // exhausted search produced no Source-Sink path.
  termination_reason_ = TerminationReason::SEARCH_COMPLETED;
  init();

  SPDLOG_INFO("\t Time (s) \t | \t Solution");
  while (fwd_search_ptr_->stop == false || bwd_search_ptr_->stop == false) {
    const Directions& direction = getDirection();
    if (direction != NODIR) {
      move(direction);
    } else {
      break;
    }
    if (terminate(direction)) {
      break;
    }
  }
  postProcessing();
  finalizeTerminationReason();
}

/* Private methods */

/* Preprocessing */

void BiDirectional::runPreprocessing() {
  if (params_ptr_->direction == BOTH && params_ptr_->find_critical_res) {
    const int c = getCriticalRes(max_res, *graph_ptr_);
    SPDLOG_INFO("Set critical resource to index {}", c);
    setCriticalRes(c);
  }
  // No need to use elementary if no negative cost cycle is found, all
  // reasources have positive values, a callback is not registered and minimum
  // resources are not present.
  detectNegativeCostCycle(graph_ptr_.get());
  if (graph_ptr_->negative_cost_cycle_present ==
          NegativeCostCyclePresent::ABSENT &&
      graph_ptr_->all_resources_positive &&
      params_ptr_->ref_callback == nullptr &&
      std::all_of(
          min_res.cbegin(), min_res.cend(), [](bool v) { return v == 0; })) {
    if (params_ptr_->elementary) {
      SPDLOG_WARN(
          "No negative cost cycle has been found and elementary set to true.\n"
          "Consider setting elementary to false.");
      // setElementary(false);
    }
  }

  if (params_ptr_->bounds_pruning) {
    SPDLOG_INFO("Setting lower bounds.");
    // checkPrimalBound completes a partial path with lower_bound_weight, so
    // the forward search needs the cost-to-go to the sink (backward shortest
    // paths) and the backward search the cost from the source (forward ones).
    if (params_ptr_->direction == BOTH || params_ptr_->direction == FWD) {
      lowerBoundWeight(
          fwd_search_ptr_->lower_bound_weight.get(), *graph_ptr_, false);
    }
    if (params_ptr_->direction == BOTH || params_ptr_->direction == BWD) {
      lowerBoundWeight(
          bwd_search_ptr_->lower_bound_weight.get(), *graph_ptr_, true);
    }
  }
}

void BiDirectional::init() {
  // Initialise labels
  labelling::Label label;
  best_label_ = std::make_shared<labelling::Label>(label);
  // Initialise resource bounds
  initResourceBounds();
  // Init individual searches
  initContainers();
  if (params_ptr_->direction == BOTH || params_ptr_->direction == FWD) {
    initSearch(FWD);
  }
  if (params_ptr_->direction == BOTH || params_ptr_->direction == BWD) {
    initSearch(BWD);
  }
  // run preprocessing
  runPreprocessing();
  // Init labels
  if (params_ptr_->direction == BOTH || params_ptr_->direction == FWD) {
    initLabels(FWD);
  }
  if (params_ptr_->direction == BOTH || params_ptr_->direction == BWD) {
    initLabels(BWD);
  }
}

void BiDirectional::initSearch(const Directions& direction) {
  Search* search_ptr = getSearchPtr(direction);
  // Allocate memory
  search_ptr->lower_bound_weight->resize(graph_ptr_->number_vertices, 0.0);
  search_ptr->efficient_labels.resize(graph_ptr_->number_vertices);
  search_ptr->best_labels.resize(graph_ptr_->number_vertices, nullptr);
}

void BiDirectional::initResourceBounds() {
  max_res_curr_ = max_res;
  min_res_curr_ = min_res;
}

void BiDirectional::initLabels(const Directions& direction) {
  Vertex              vertex;
  std::vector<double> res(min_res.size(), 0.0);
  std::vector<int>    path;
  Search*             search_ptr       = getSearchPtr(direction);
  const int           size_unreachable = graph_ptr_->number_vertices + 1;

  if (direction == FWD) {
    vertex = graph_ptr_->source;
  } else { // backward
    // set monotone resource to upper bound
    res[params_ptr_->critical_res] = max_res_curr_[params_ptr_->critical_res];
    vertex                         = graph_ptr_->sink;
  }
  // Current label init
  path = {vertex.user_id};
  labelling::Label lab(0.0, vertex, res, path, params_ptr_.get());
  search_ptr->replaceCurrentLabel(lab);
  // Final label dummy init
  Vertex dum_vertex = {-1, -1};
  res               = {};
  path              = {};
  labelling::Label lab2(0.0, dum_vertex, res, path, params_ptr_.get());

  search_ptr->replaceIntermediateLabel(lab2);
  search_ptr->pushHeap();
  // Add to efficient and best labels
  search_ptr->pushEfficientLabel(vertex.lemon_id, *search_ptr->current_label);
  search_ptr->replaceBestLabel(vertex.lemon_id, *search_ptr->current_label);
  search_ptr->addVisitedVertex(vertex.lemon_id);
}

void BiDirectional::initContainers() {
  if (params_ptr_->direction != BOTH) {
    Search* search_ptr = getSearchPtr(params_ptr_->direction);
    search_ptr->makeHeap();
  } else {
    fwd_search_ptr_->makeHeap();
    bwd_search_ptr_->makeHeap();
  }
}

/* Search */

Directions BiDirectional::getDirection() const {
  if (params_ptr_->direction == BOTH) {
    if (!fwd_search_ptr_->stop && bwd_search_ptr_->stop) {
      return FWD;
    } else if (fwd_search_ptr_->stop && !bwd_search_ptr_->stop) {
      return BWD;
    } else if (!fwd_search_ptr_->stop && !bwd_search_ptr_->stop) {
      // TODO: fix random
      // if (method == "random") {
      //   // return a random direction
      //   const std::vector<std::string> directions = {forward,
      //   backward}; const int                      r          =
      //   std::rand() % 2; const std::string&             direction  =
      //   directions[r]; return direction;
      // } else
      if (params_ptr_->method == "generated") {
        // return direction with least number of generated labels
        if (fwd_search_ptr_->generated_count <
            bwd_search_ptr_->generated_count) {
          return FWD;
        }
        return BWD;
      } else if (params_ptr_->method == "processed") {
        // return direction with least number of processed labels
        if (fwd_search_ptr_->processed_count <
            bwd_search_ptr_->processed_count) {
          return FWD;
        }
        return BWD;
      } else if (params_ptr_->method == "unprocessed") {
        // return direction with least number of unprocessed labels
        if (fwd_search_ptr_->unprocessed_count <
            bwd_search_ptr_->unprocessed_count) {
          return FWD;
        }
        return BWD;
      }
    } else {
      ;
    }
  } else {
    // Single direction
    if (params_ptr_->direction == FWD && fwd_search_ptr_->stop) {
      ;
    } else if (params_ptr_->direction == BWD && bwd_search_ptr_->stop) {
      ;
    } else {
      return params_ptr_->direction;
    }
  }
  return NODIR;
}

void BiDirectional::move(const Directions& direction) {
  Search*     search_ptr      = getSearchPtr(direction);
  const bool& bounds_exceeded = checkBounds(direction);
  if (!bounds_exceeded) {
    extendCurrentLabel(direction);
    saveCurrentBestLabel(direction);
  } else {
    search_ptr->stop = true;
  }
  updateHalfWayPoints(direction);
  updateCurrentLabel(direction);
  ++search_ptr->processed_count;
  ++iteration_;
}

bool BiDirectional::terminate(const Directions& direction) {
  Search* search_ptr = getSearchPtr(direction);
  return terminate(direction, *search_ptr->intermediate_label);
}

bool BiDirectional::terminate(
    const Directions&       direction,
    const labelling::Label& label) {
  // Check time elapsed (if relevant)
  const double& timediff_sec = getElapsedTime();
  if (!std::isnan(params_ptr_->time_limit) &&
      timediff_sec >= params_ptr_->time_limit) {
    termination_reason_ = TerminationReason::TIME_LIMIT_REACHED;
    return true;
  }
  return checkValidLabel(direction, label);
}

void BiDirectional::updateCurrentLabel(const Directions& direction) {
  Search* search_ptr = getSearchPtr(direction);
  if (search_ptr->unprocessed_labels->size() > 0) {
    // Get next label and removes current_label from heap
    const labelling::Label& new_label = labelling::getNextLabel(
        search_ptr->unprocessed_labels.get(), direction);
    // swap current label with new label
    search_ptr->replaceCurrentLabel(new_label);
    // Update unprocessed label counter
    search_ptr->unprocessed_count = search_ptr->unprocessed_labels->size();
    SPDLOG_DEBUG("{} left in {}", search_ptr->unprocessed_count, direction);
  } else {
    search_ptr->stop = true;
  }
}

/* Checks */
bool BiDirectional::checkValidLabel(
    const Directions&       direction,
    const labelling::Label& label) {
  if (label.vertex.lemon_id != -1 &&
      label.checkStPath(graph_ptr_->source.user_id, graph_ptr_->sink.user_id)) {
    if (!std::isnan(params_ptr_->threshold) &&
        label.checkThreshold(
            params_ptr_->threshold, params_ptr_->threshold_strict)) {
      terminated_early_w_st_path_           = true;
      terminated_early_w_st_path_direction_ = direction;
      termination_reason_ = TerminationReason::THRESHOLD_REACHED;
      return true;
    }
  }
  return false;
}

bool BiDirectional::checkBounds(const Directions& direction) {
  // Check resource bounds
  Search*    search_ptr = getSearchPtr(direction);
  const int& c_res      = params_ptr_->critical_res;

  if ((direction == FWD &&
       search_ptr->current_label->resource_consumption[c_res] <=
           max_res_curr_[c_res]) ||
      (direction == BWD &&
       search_ptr->current_label->resource_consumption[c_res] >
           min_res_curr_[c_res]) ||
      max_res_curr_[c_res] != min_res_curr_[c_res]) {
    return false;
  }
  // only stop if search is being performed in both directions
  else if (params_ptr_->direction == BOTH) {
    return true;
  }
  return false;
}

bool BiDirectional::checkPrimalBound(
    const Directions&       direction,
    const labelling::Label& candidate_label) {
  Search* search_ptr = getSearchPtr(direction);
  const std::unique_ptr<std::vector<double>>& lower_bound_weight =
      search_ptr->lower_bound_weight;
  if (!params_ptr_->bounds_pruning) {
    return false;
  }
  if (!std::isnan(primal_st_bound_) &&
      candidate_label.weight +
              (*lower_bound_weight)[candidate_label.vertex.lemon_id] >
          primal_st_bound_) {
    return true;
  }
  return false;
}

bool BiDirectional::checkVertexVisited(
    const Directions& direction,
    const int&        vertex_idx) {
  Search* search_ptr = getSearchPtr(direction);
  return (
      search_ptr->visited_vertices.find(vertex_idx) !=
      search_ptr->visited_vertices.end());
}

void BiDirectional::updateHalfWayPoints(const Directions& direction) {
  Search*    search_ptr = getSearchPtr(direction);
  const int& c_res      = params_ptr_->critical_res;
  if (direction == FWD) {
    min_res_curr_[c_res] = std::max(
        min_res_curr_[c_res],
        std::min(
            search_ptr->current_label->resource_consumption[c_res],
            max_res_curr_[c_res]));
  } else {
    max_res_curr_[c_res] = std::min(
        max_res_curr_[c_res],
        std::max(
            search_ptr->current_label->resource_consumption[c_res],
            min_res_curr_[c_res]));
  }
}

void BiDirectional::extendCurrentLabel(const Directions& direction) {
  // Extend and check current resource feasibility for each edge
  Search*                            search_ptr    = getSearchPtr(direction);
  std::shared_ptr<labelling::Label>& current_label = search_ptr->current_label;
  SPDLOG_DEBUG("Extending: {}", current_label->getString());
  if (direction == FWD) {
    // For each outgoing arc from the current label
    for (LemonGraph::OutArcIt a(
             *graph_ptr_->lemon_graph_ptr,
             graph_ptr_->getLNodeFromId(current_label->vertex.lemon_id));
         a != lemon::INVALID;
         ++a) {
      const AdjVertex& adj_v = graph_ptr_->getAdjVertex(a, true);
      SPDLOG_DEBUG(
          "\t Along: {}->{}",
          current_label->vertex.user_id,
          adj_v.vertex.user_id);
      extendSingleLabel(current_label.get(), direction, adj_v);
    }
  } else {
    // For each incoming arc to the current label
    for (LemonGraph::InArcIt a(
             *graph_ptr_->lemon_graph_ptr,
             graph_ptr_->getLNodeFromId(current_label->vertex.lemon_id));
         a != lemon::INVALID;
         ++a) {
      const AdjVertex& adj_v = graph_ptr_->getAdjVertex(a, false);
      SPDLOG_DEBUG(
          "\t Along: {}->{}",
          current_label->vertex.user_id,
          adj_v.vertex.user_id);
      extendSingleLabel(current_label.get(), direction, adj_v);
    }
  }
}

void BiDirectional::extendSingleLabel(
    labelling::Label* label,
    const Directions& direction,
    const AdjVertex&  adj_vertex) {
  // Mandatory visits: never reach the sink before every required node has
  // been visited. Guarded, hence a no-op by default.
  if (params_ptr_->require_all_visits && direction == FWD &&
      adj_vertex.vertex.user_id == graph_ptr_->sink.user_id &&
      !label->checkAllRequiredVisited()) {
    return;
  }
  if ( // Always extend when non-elementary
      !params_ptr_->elementary ||
      // When elementary, check if vertex already seen / unreachable and if the
      // next node is suitable (2-cycles are not allowed!)
      (params_ptr_->elementary &&
       label->unreachable_nodes.find(adj_vertex.vertex.user_id) ==
           label->unreachable_nodes.end())) {
    if (label->partial_path.size() <= 1 ||
        (label->partial_path.size() > 1 &&
         label->checkPathExtension(adj_vertex.vertex.user_id))) {
      // extend current label along edge
      labelling::Label new_label =
          label->extend(adj_vertex, direction, max_res_curr_, min_res_curr_);

      // If label non-empty, (only when the extension is resource-feasible)
      if (new_label.vertex.lemon_id != -1) {
        SPDLOG_DEBUG("\t Found new label: {}", new_label.getString());
        updateEfficientLabels(direction, new_label);
      } else {
        SPDLOG_DEBUG("\t Extension infeasible");
      }
    }
  }
}

void BiDirectional::updateEfficientLabels(
    const Directions&       direction,
    const labelling::Label& candidate_label) {
  Search* search_ptr = getSearchPtr(direction);
  // const ref vertex index
  const int& lemon_id = candidate_label.vertex.lemon_id;
  // ref efficient_labels_ for a given vertex
  std::vector<labelling::Label>& efficient_labels_vertex =
      search_ptr->efficient_labels[lemon_id];

  if (std::find(
          efficient_labels_vertex.begin(),
          efficient_labels_vertex.end(),
          candidate_label) == efficient_labels_vertex.end()) {
    ++search_ptr->generated_count;
    // If there already exists labels for the given vertex
    if (efficient_labels_vertex.size() > 1) {
      // check if new_label is dominated by any other comparable label
      const bool dominated = runDominanceEff(
          &efficient_labels_vertex,
          candidate_label,
          direction,
          params_ptr_->elementary);
      if (!dominated && !checkPrimalBound(direction, candidate_label)) {
        // add candidate_label to efficient_labels and unprocessed heap
        search_ptr->pushEfficientLabel(lemon_id, candidate_label);
        search_ptr->pushUnprocessedLabel(candidate_label);
        SPDLOG_DEBUG("\t Added to the queue.");
      } else {
        SPDLOG_DEBUG("\t Label dominated.");
      }
    } else {
      // First label produced for the vertex
      // update both efficient and unprocessed labels
      search_ptr->pushEfficientLabel(lemon_id, candidate_label);
      search_ptr->pushUnprocessedLabel(candidate_label);
      SPDLOG_DEBUG("\t Added to the queue (no other label at this vertex).");
    }
    updateBestLabels(direction, candidate_label);
    // Update vertices visited
    search_ptr->addVisitedVertex(lemon_id);
  }
}

void BiDirectional::updateBestLabels(
    const Directions&       direction,
    const labelling::Label& candidate_label) {
  // Only save full paths when they are global resource feasible
  Search*    search_ptr = getSearchPtr(direction);
  const int& lemon_id   = candidate_label.vertex.lemon_id;
  std::vector<std::shared_ptr<labelling::Label>>& best_labels =
      search_ptr->best_labels;

  bool stop = false;
  if (direction == FWD && lemon_id == graph_ptr_->sink.lemon_id &&
      !candidate_label.checkFeasibility(max_res, min_res)) {
    stop = true;
  } else if (
      direction == BWD && lemon_id == graph_ptr_->source.lemon_id &&
      !candidate_label.checkFeasibility(max_res, min_res)) {
    stop = true;
  }
  if (stop) {
    SPDLOG_DEBUG("\t Label not globally feasible and not s-t path.");
    return;
  }
  // Update best_label only when new label has lower weight or first label
  if ((best_labels[lemon_id] &&
       candidate_label.weight < best_labels[lemon_id]->weight) ||
      !best_labels[lemon_id]) {
    search_ptr->replaceBestLabel(lemon_id, candidate_label);
    SPDLOG_DEBUG(
        "\t Vertex improvement with {}.",
        search_ptr->best_labels[lemon_id]->getString());
  }
}

void BiDirectional::saveCurrentBestLabel(const Directions& direction) {
  Search* search_ptr = getSearchPtr(direction);

  std::shared_ptr<labelling::Label>& intermediate_label_ptr =
      search_ptr->intermediate_label;
  std::shared_ptr<labelling::Label>& current_label_ptr =
      search_ptr->current_label;

  if (intermediate_label_ptr->vertex.lemon_id == -1) {
    intermediate_label_ptr =
        std::make_shared<labelling::Label>(*current_label_ptr);
    return;
  }
  // Check for global feasibility
  if (!current_label_ptr->checkFeasibility(max_res, min_res)) {
    return;
  }
  bool improvement_found = false;
  if (intermediate_label_ptr->vertex.lemon_id ==
          current_label_ptr->vertex.lemon_id &&
      current_label_ptr->fullDominance(*intermediate_label_ptr, direction)) {
    // Save complete source-sink path
    search_ptr->replaceIntermediateLabel(*current_label_ptr);
    improvement_found = true;
  } else {
    // First source-sink path
    if ((direction == FWD &&
         (current_label_ptr->partial_path.back() == graph_ptr_->sink.user_id &&
          intermediate_label_ptr->vertex.user_id ==
              graph_ptr_->source.user_id)) ||
        (direction == BWD && (current_label_ptr->partial_path.back() ==
                                  graph_ptr_->source.user_id &&
                              intermediate_label_ptr->vertex.user_id ==
                                  graph_ptr_->sink.user_id))) {
      // Save complete source-sink path
      search_ptr->replaceIntermediateLabel(*current_label_ptr);
      improvement_found = true;
      // Update bounds
      if (std::isnan(primal_st_bound_) ||
          intermediate_label_ptr->weight < primal_st_bound_) {
        primal_st_bound_ = intermediate_label_ptr->weight;
      }
    }
  }

  if (improvement_found) {
    SPDLOG_INFO(
        "\t {} \t | \t {}", getElapsedTime(), current_label_ptr->weight);
    SPDLOG_DEBUG(
        "******* Global improvement {}.",
        search_ptr->intermediate_label->getString());
  }
}

/**
 * Post-processing methods
 */

void BiDirectional::postProcessing() {
  if (!terminated_early_w_st_path_) {
    if (params_ptr_->direction == BOTH) {
      // If bidirectional algorithm used and both directions traversed, run
      // path joining procedure.
      joinLabels();
    } else {
      // If FWD direction specified or backward direction not traversed
      if (params_ptr_->direction == FWD) {
        // Forward
        best_label_ = fwd_search_ptr_->intermediate_label;
      }
      // If backward direction specified or FWD direction not traversed
      else {
        // Backward
        best_label_ =
            std::make_shared<labelling::Label>(labelling::processBwdLabel(
                *bwd_search_ptr_->intermediate_label, max_res, min_res, true));
      }
    }
  } else {
    // final label contains the label that triggered the early termination
    if (terminated_early_w_st_path_direction_ == FWD) {
      best_label_ = fwd_search_ptr_->intermediate_label;
    } else {
      best_label_ =
          std::make_shared<labelling::Label>(labelling::processBwdLabel(
              *bwd_search_ptr_->intermediate_label, max_res, min_res, true));
    }
  }
  // Mandatory visits: safety net turning a silently wrong answer into a
  // loud failure. Guarded, hence a no-op by default.
  if (params_ptr_->require_all_visits && best_label_ &&
      best_label_->vertex.lemon_id != -1 &&
      best_label_->checkStPath(
          graph_ptr_->source.user_id, graph_ptr_->sink.user_id) &&
      !best_label_->checkAllRequiredVisited()) {
    throw std::runtime_error(
        "[BiDirectional] internal error: the returned path does not visit all"
        " required nodes");
  }
  // 80 stars at the end
  spdlog::default_logger()->set_pattern("%v");
  SPDLOG_INFO(
      "************************************************************************"
      "********");
}

void BiDirectional::finalizeTerminationReason() {
  // Early stops (threshold, time limit) already carry their final reason.
  if (termination_reason_ != TerminationReason::SEARCH_COMPLETED) {
    return;
  }
  // The search ran to exhaustion; decide between "completed" (a Source-Sink
  // path was found) and "no_feasible_path" (none exists). Guard against the
  // dummy label (lemon_id == -1, empty path) left when no path was found:
  // checkStPath reads partial_path[0] and must not be called on it.
  const bool found_source_sink_path =
      (best_label_ && best_label_->vertex.lemon_id != -1 &&
       !best_label_->partial_path.empty() &&
       best_label_->checkStPath(
           graph_ptr_->source.user_id, graph_ptr_->sink.user_id));
  if (!found_source_sink_path) {
    termination_reason_ = TerminationReason::NO_FEASIBLE_PATH;
  }
}

double BiDirectional::getUB() {
  double UB = std::numeric_limits<double>::infinity();
  // Extract forward and backward best labels (one's with least weight)
  const auto& fwd_best =
      fwd_search_ptr_->best_labels[graph_ptr_->sink.lemon_id];
  const auto& bwd_best =
      bwd_search_ptr_->best_labels[graph_ptr_->source.lemon_id];
  // Upper bound must be a resource-feasible s-t path
  if (fwd_best && fwd_best->checkFeasibility(max_res, min_res)) {
    UB = fwd_best->weight;
  }
  if (bwd_best && bwd_best->checkFeasibility(max_res, min_res)) {
    if (bwd_best->weight < UB) {
      UB = bwd_best->weight;
    }
  }
  return UB;
}

void BiDirectional::getMinimumWeights(double* fwd_min, double* bwd_min) {
  // Forward
  // init
  *fwd_min = std::numeric_limits<double>::infinity();
  for (const int& n : fwd_search_ptr_->visited_vertices) {
    if (n != graph_ptr_->source.lemon_id && fwd_search_ptr_->best_labels[n] &&
        fwd_search_ptr_->best_labels[n]->weight < *fwd_min) {
      *fwd_min = fwd_search_ptr_->best_labels[n]->weight;
    }
  }
  // backward
  *bwd_min = std::numeric_limits<double>::infinity();
  for (const int& n : bwd_search_ptr_->visited_vertices) {
    if (n != graph_ptr_->sink.lemon_id && bwd_search_ptr_->best_labels[n] &&
        bwd_search_ptr_->best_labels[n]->weight < *bwd_min) {
      *bwd_min = bwd_search_ptr_->best_labels[n]->weight;
    }
  }
}

void BiDirectional::joinLabels() {
  // ref id with critical_res
  SPDLOG_INFO("Merging");
  const int&    c_res   = params_ptr_->critical_res;
  double        UB      = getUB();
  const double& HF      = std::min(max_res_curr_[c_res], min_res_curr_[c_res]);
  auto          fwd_min = std::make_unique<double>();
  auto          bwd_min = std::make_unique<double>();
  // lower bounds on forward and backward labels
  getMinimumWeights(fwd_min.get(), bwd_min.get());

  std::vector<labelling::Label> merged_labels_;

  // for each vertex visited forward
  for (const int& n : fwd_search_ptr_->visited_vertices) {
    // if bound check fwd_label
    // Defensive null guard: best_labels[n] may be unset when no globally
    // feasible label reached n (see updateBestLabels early return).
    if (fwd_search_ptr_->best_labels[n] &&
        fwd_search_ptr_->best_labels[n]->weight + *bwd_min <= UB &&
        n != graph_ptr_->sink.lemon_id) {
      // for each forward label at n
      for (auto fwd_iter = fwd_search_ptr_->efficient_labels[n].cbegin();
           fwd_iter != fwd_search_ptr_->efficient_labels[n].cend();
           ++fwd_iter) {
        const labelling::Label& fwd_label = *fwd_iter;
        // if bound check fwd_label
        if (fwd_label.resource_consumption[c_res] <= HF &&
            fwd_label.weight + *bwd_min <= UB) {
          // for each successor of n
          for (LemonGraph::OutArcIt a(
                   *graph_ptr_->lemon_graph_ptr, graph_ptr_->getLNodeFromId(n));
               a != lemon::INVALID;
               ++a) {
            const int&    m           = graph_ptr_->getId(graph_ptr_->head(a));
            const double& edge_weight = graph_ptr_->getWeight(a);
            if (checkVertexVisited(BWD, m) &&
                m != graph_ptr_->source.lemon_id &&
                bwd_search_ptr_->best_labels[m] &&
                (fwd_label.weight + edge_weight +
                     bwd_search_ptr_->best_labels[m]->weight <=
                 UB)) {
              // for each backward label at m
              for (auto bwd_iter =
                       bwd_search_ptr_->efficient_labels[m].cbegin();
                   bwd_iter != bwd_search_ptr_->efficient_labels[m].cend();
                   ++bwd_iter) {
                const labelling::Label& bwd_label = *bwd_iter;
                // TODO: should suffice with strict > HF, but Beasley 10
                // fails
                if (bwd_label.resource_consumption[c_res] >= HF &&
                    (fwd_label.weight + edge_weight + bwd_label.weight <= UB) &&
                    labelling::mergePreCheck(fwd_label, bwd_label, max_res)) {
                  const labelling::Label& merged_label = labelling::mergeLabels(
                      fwd_label,
                      bwd_label,
                      graph_ptr_->getAdjVertex(a, true),
                      graph_ptr_->sink,
                      max_res,
                      min_res);
                  if (merged_label.vertex.lemon_id != -1 &&
                      merged_label.checkFeasibility(max_res, min_res) &&
                      labelling::halfwayCheck(merged_label, merged_labels_)) {
                    if (best_label_->vertex.lemon_id == -1 ||
                        (merged_label.fullDominance(*best_label_, FWD) ||
                         merged_label.weight < best_label_->weight)) {
                      // Save
                      best_label_ =
                          std::make_shared<labelling::Label>(merged_label);
                      SPDLOG_INFO(
                          "\t {} \t | \t {}",
                          getElapsedTime(),
                          best_label_->weight);
                      // Tighten UB
                      if (best_label_->weight < UB) {
                        UB = best_label_->weight;
                      }
                      // Stop if time out or threshold found
                      if (terminate(FWD, *best_label_)) {
                        return;
                      }
                    }
                  }
                  // Add merged label to list
                  merged_labels_.push_back(merged_label);
                } // else
                  // break;
              }
            }
          }
        } // else
          // break;
      }
    }
  }
} // end joinLabels

} // namespace bidirectional
