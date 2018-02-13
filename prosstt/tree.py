#!/usr/bin/env python
# coding: utf-8

"""
This module contains the definition of the Tree class. The Tree class describes
a lineage tree. Each object contains information about the topology
of the lineage tree and the gene expression for each gene at each point of the
tree.
"""

from collections import defaultdict
import numpy as np
import pandas as pd
import newick
from prosstt import tree_utils as tu

class Tree(object):
    'topology of the differentiation tree'

    # default values for when the user is not decided
    def_time = 40
    def_comp = 15
    def_genes = 500

    def __init__(self, topology=[["A", "B"], ["A", "C"]],
                 time={"A":def_time, "B":def_time, "C":def_time},
                 num_branches=3,
                 branch_points=1,
                 modules=def_comp,
                 G=def_genes,
                 density=None,
                 root=None):
        self.topology = topology
        self.time = pd.Series(time, name="time")
        self.num_branches = num_branches
        self.branch_points = branch_points
        self.modules = modules
        self.G = G
        self.means = None
        self.branches = list(time.keys())

        if root is None:
            self.root = self.branches[0]
        else:
            self.root = root

        if density is None:
            self.density = self.default_density()
        else:
            self.density = density

    @staticmethod
    def gen_random_topology(branch_points):
        """
        Generates a random topology for a lineage tree. At every branch point
        a bifurcation is taking place.

        Parameters
        ----------
        branch_points: int
            The number of branch points in the topology
        """
        total_branches = 2 * branch_points + 1
        seeds = [0]
        avail = list(reversed(range(1, total_branches)))
        res = []
        while avail:
            root = np.random.choice(seeds)
            branch_a = avail.pop()
            branch_b = avail.pop()
            res.append([root, branch_a])
            res.append([root, branch_b])
            seeds.append(branch_a)
            seeds.append(branch_b)
            seeds.remove(root)
        return res

    @classmethod
    def from_newick(cls, newick_tree,
                    modules=10,
                    genes=200,
                    density=None):
        """
        Generate a lineage tree from a Newick-formatted string.
        """
        tree = newick.loads(newick_tree)
        top, time, branches, br_points, root = tu.parse_newick(tree, cls.def_time)
        tree = Tree(top, time, branches, br_points, modules, genes, density, root)
        return tree

    @classmethod
    def from_random_topology(cls, branch_points, time, modules, genes):
        """
        Generate a random binary tree topology given a number of branch points.
        """
        topology = Tree.gen_random_topology(branch_points)
        branches = len(np.unique(topology))
        return cls(topology, time, branches, branch_points, modules, genes)

    def default_density(self):
        """
        Initializes the density with a uniform distribution (every cell has the
        same probability of being picked. This is in case the users want to use
        the density sampling function.
        """
        total_time = 0
        density = {}
        for branch_time in self.time.values:
            total_time += branch_time

        for k in self.time.keys():
            density[k] = np.array([1. / total_time] * np.int(self.time[k]))
        return density

    def add_genes(self, average_expression):
        """
        Sets the average gene expression trajectories of genes for all branches
        after performing a sanity check.

        Parameters
        ----------
        average_expression: float array
            A list of arrays. List length is #branches and array
            average_expression[b] has the dimensions time[b], G.
        """
        # sanity check of dimensions so that in case a user messes up there is
        # no cryptic IndexOutOfBounds exception they have to trace.
        if not len(average_expression) == self.num_branches:
            msg = "The number of arrays in average_expression must be equal to \
                   the number of branches in the topology"
            raise ValueError(msg)

        for branch in average_expression:
            mean = average_expression[branch]
            if not mean.shape == (self.time[branch], self.G):
                msg = "Branch " + branch + " was expected to have a shape " \
                        + str((self.time[branch], self.G)) + " and instead is " \
                        + str(mean.shape)
                raise ValueError(msg)

        self.means = average_expression

    def set_density(self, density):
        """
        Sets the density as a function of the pseudotime and the branching. If
        N points from the tree were picked randomly, then the density is the
        probability of a pseudotime point in a certain branch being picked.

        Parameters
        ----------
        density: dict
            The density of each branch. For each branch b, len(density[b]) must
            equal tree.time[b].
        """
        if not len(density) == self.branches:
            msg = "The number of arrays in density must be equal to the number \
                  of branches in the topology"
            raise ValueError(msg)
        for i, branch_density in enumerate(density):
            if not len(branch_density) == self.time[i]:
                msg = "Branch " + str(i) + " was expected to have a length " \
                      + str((self.time[i], self.G)) + " and instead is " \
                      + str(branch_density.shape)
                raise ValueError(msg)
        self.density = density

    def get_max_time(self):
        """
        Calculate the maximum pseudotime duration possible for the tree.

        Returns
        -------
        start: str
            Name of the starting node.
        """
        # find paths to leaves in dict:
        tree_paths = self.paths(self.root)

        total_lengths = np.zeros(len(tree_paths))

        for i, path in enumerate(tree_paths):
            path_length = [self.time[branch] for branch in path]
            total_lengths[i] = np.sum(path_length)

        return int(np.max(total_lengths))

    def as_dictionary(self):
        """
        Converts the tree topology to a dictionary where the ID of every branch
        points to the branches that bifurcate from it.

        Returns
        -------
        dict
            The topology of the tree in dictionary form.
        """
        treedict = defaultdict(list)
        for branch_pair in self.topology:
            treedict[branch_pair[0]].append(branch_pair[1])
        return(treedict)

    def paths(self, start):
        """
        Finds all paths from a given start point to the leaves.

        Parameters
        ----------
        start: str
            The starting point.

        Returns
        -------
        rooted_paths: int array
            An array that contains all paths from the starting point to all
            tree leaves.
        """
        # make a list of all possible paths through the tree
        # and calculate the length of those paths, then keep max
        # first take topology and make it a dictionary:
        treedict = self.as_dictionary()
        if not treedict[start]:
            return [[start]]
        else:
            rooted_paths = []
            root = [start]
            for node in treedict[start]:
                usable = self.paths(node)
                for path in usable:
                    rooted_paths.append(root + path)
            return rooted_paths

    def populate_timezone(self):
        """
        Returns an array that assigns pseudotime to time zones.

        This function first determines the timezones by considering the length
        of the branches and then assigns a timezone to each pseudotime range.
        E.g. for Ts = [25, 25, 30] we would have timezone[0:24] = 0,
        timezone[25:49] = 1, timezone[50:54] = 2.

        Returns
        -------
        timezone: int array
            Array of length total_time, contains the timezone information for
            each pseudotime point.
        updated_Ts: int array
            Converts from relative time to absolute time: given
            Ts=[25,25,25,25,25] branch 0 starts at pseudotime 0, but branches 1
            and 2 start at pseudotime 25 and branches 3,4 at pseudotime 50.
        """
        res = []
        tpaths = self.paths(self.root)
        stacks = [self.morph_stack(self.time[x].tolist()) for x in tpaths]

        while stacks:
            lpaths = len(stacks)
            curr = [stacks[i][0] for i in range(lpaths)]
            starts = np.array([curr[i][0] for i in range(lpaths)])
            ends = np.array([curr[i][1] for i in range(lpaths)])

            if all(ends == np.max(ends)):
                res.append([np.max(starts), np.max(ends) - 1])
                for stack in stacks:
                    stack.pop(0)
            else:
                res.append([np.max(starts), np.min(ends) - 1])
                for stack in stacks:
                    if stack[0][1] != np.min(ends):
                        stack.insert(1, [np.min(ends), stack[0][1]])
                    stack.pop(0)

            newstacks = [x for x in stacks if x]
            stacks = newstacks
        return res

    def branch_times(self):
        """
        Calculates the pseudotimes at which branches start and end.

        Returns
        -------
        branch_time: dict
            Dictionary that contains the start and end time for every branch.

        Examples
        --------
        >>> from prosstt.tree import Tree
        >>> t = Tree.from_topology([[0,1], [0,2]])
        >>> t.branch_times()
        defaultdict(<class 'list'>, {0: [0, 39], 1: [40, 79], 2: [40, 79]})
        """
        branch_time = defaultdict(list)

        branch_time[self.root] = [0, self.time[self.root] - 1]
        for branch_pair in self.topology:
            # the start time of b[1] is the end time of b[0]
            b0_end = branch_time[branch_pair[0]][1]
            branch_time[branch_pair[1]] = [b0_end + 1, b0_end + self.time[branch_pair[1]]]
        return branch_time

    # stacks = [self.morph_stack(ntime[np.array(x)].tolist()) for x in tpaths]
    def morph_stack(self, stack):
        """
        The pseudotime start and end of every branch in a path. Very similar to
        branch_times().

        Parameters
        ----------
        stack: int array
            The pseudotime length of all branches that make up a path in the
            tree (from the origin to a leaf).

        Returns
        -------
        stack: list of 2D arrays
            The pseudotime start and end of every branch in the path.
        """
        curr = 0
        prev = 0
        for i, curr in enumerate(stack):
            stack[i] = [prev, prev + stack[i]]
            prev = curr + prev
        return stack

    def get_parallel_branches(self):
        """
        Find the branches that run in parallel (i.e. share a parent branch).
        """
        top_array = np.array(self.topology)
        parallel = {}
        for branch in np.unique(top_array[:, 0]):
            matches = top_array[:, 0] == branch
            parallel[branch] = top_array[matches, 1]
        return parallel
