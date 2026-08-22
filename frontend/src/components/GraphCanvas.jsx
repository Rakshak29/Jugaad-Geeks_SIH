import React, { useEffect, useRef } from 'react';
import * as d3 from 'd3';

const GraphCanvas = ({ data, onNodeClick, selectedNodeId, simulationState }) => {
  const svgRef = useRef();
  const containerRef = useRef();
  
  const gRef = useRef(null);
  const nodeRef = useRef(null);
  const linkRef = useRef(null);

  useEffect(() => {
    if (!data || !data.nodes || !data.links) return;

    const width = containerRef.current.clientWidth;
    const height = containerRef.current.clientHeight;

    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove(); 

    const nodes = data.nodes.map(d => {
      const obj = Object.create(d);
      // Determine tier for charge and radius
      if (d.type === 'SYSTEM' || d.type === 'EMPLOYEE') obj.tier = 0;
      else if (d.type === 'COMPONENT' || d.type === 'CAPABILITY') obj.tier = 1;
      else obj.tier = 2;
      return obj;
    });
    
    const links = data.links.map(d => Object.create(d));

    const g = svg.append('g');
    gRef.current = g;

    const zoom = d3.zoom()
      .scaleExtent([0.1, 4])
      .on('zoom', (event) => {
        g.attr('transform', event.transform);
      });
    svg.call(zoom);

    const degree = {};
    nodes.forEach(n => degree[n.id] = 0);
    links.forEach(l => {
      degree[l.source] = (degree[l.source] || 0) + 1;
      degree[l.target] = (degree[l.target] || 0) + 1;
    });

    const getRadius = (d) => {
      if (d.tier === 0) return 22;
      if (d.tier === 1) return 14;
      return 8;
    };

    const getCollideRadius = (d) => {
      if (d.type === 'EMPLOYEE') return 80; 
      if (d.type === 'SYSTEM') return 80;
      return getRadius(d) + 25;
    };

    const simulation = d3.forceSimulation(nodes)
      .force('link', d3.forceLink(links).id(d => d.id).distance(220).strength(1))
      .force('charge', d3.forceManyBody().strength(d => d.tier === 0 ? -1200 : -600))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collide', d3.forceCollide(d => getCollideRadius(d)).strength(1))
      .force('x', d3.forceX(width / 2).strength(0.08));

    // Semantic Y positioning for Technical Graph
    simulation.force('y', d3.forceY().y(d => {
      if (data.graphType === 'technical') {
        if (d.type === 'SYSTEM') return height * 0.2;
        if (d.type === 'COMPONENT') return height * 0.8;
      } else if (data.graphType === 'knowledge') {
        if (d.type === 'EMPLOYEE') return height * 0.3;
        if (d.type === 'CAPABILITY') return height * 0.7;
      }
      return height / 2;
    }).strength(0.4));

    const link = g.append('g')
      .selectAll('path')
      .data(links)
      .join('path')
      .attr('stroke', d => data.graphType === 'knowledge' ? '#4ade80' : '#68675f')
      .attr('fill', 'none')
      .attr('stroke-width', 1.5)
      .attr('opacity', 0.6);
    linkRef.current = link;

    const node = g.append('g')
      .selectAll('g')
      .data(nodes)
      .join('g')
      .attr('class', 'node')
      .attr('cursor', 'pointer')
      .call(drag(simulation));
    nodeRef.current = node;

    const getNodeColor = (d) => {
      // Technical graph
      if (d.type === 'SYSTEM') return '#5b9cf2'; // blue
      if (d.type === 'COMPONENT') return '#f2b84b'; // amber
      
      // Knowledge graph
      if (d.type === 'EMPLOYEE') return '#5b9cf2'; // blue (Engineer)
      if (d.type === 'CAPABILITY') return '#4ade80'; // green (Capability)
      if (d.type === 'EVIDENCE') return '#b18af2'; // purple (Work item)
      
      return '#7a5f96';
    };

    node.append('circle')
      .attr('r', d => getRadius(d))
      .attr('fill', d => getNodeColor(d))
      .attr('stroke', '#0a0a0b')
      .attr('stroke-width', 2);

    node.append('text')
      .text(d => d.label)
      .attr('x', 0)
      .attr('y', d => -(getRadius(d) + 8))
      .attr('text-anchor', 'middle')
      .attr('fill', '#eceae4')
      .style('font-size', '11px')
      .style('font-family', '-apple-system, Arial, sans-serif')
      .style('pointer-events', 'none');

    simulation.on('tick', () => {
      link.attr('d', d => {
        // Cubic bezier (S-curve) for beautiful hierarchical connections
        const midY = (d.source.y + d.target.y) / 2;
        return `M${d.source.x},${d.source.y} C${d.source.x},${midY} ${d.target.x},${midY} ${d.target.x},${d.target.y}`;
      });
      node.attr('transform', d => `translate(${d.x},${d.y})`);
    });

    // Let the simulation settle and completely freeze
    simulation.alphaDecay(0.05);

    node.on('click', (event, d) => {
      onNodeClick(data.nodes.find(n => n.id === d.id));
    });

    function drag(simulation) {
      function dragstarted(event) {
        if (!event.active) simulation.alphaTarget(0.35).restart();
        event.subject.fx = event.subject.x;
        event.subject.fy = event.subject.y;
      }
      function dragged(event) {
        event.subject.fx = event.x;
        event.subject.fy = event.y;
      }
      function dragended(event) {
        if (!event.active) simulation.alphaTarget(0);
        event.subject.fx = null;
        event.subject.fy = null;
      }
      return d3.drag().on('start', dragstarted).on('drag', dragged).on('end', dragended);
    }

    return () => simulation.stop();
  }, [data]);

  useEffect(() => {
    if (!nodeRef.current || !linkRef.current) return;
    
    // Compute neighbors for fast lookup
    const neighbors = new Set();
    if (selectedNodeId) {
      neighbors.add(selectedNodeId);
      data.links.forEach(l => {
        const sourceId = typeof l.source === 'object' ? l.source.id : l.source;
        const targetId = typeof l.target === 'object' ? l.target.id : l.target;
        if (sourceId === selectedNodeId) neighbors.add(targetId);
        if (targetId === selectedNodeId) neighbors.add(sourceId);
      });
    }

    const getNodeColor = (d) => {
      if (simulationState) {
        if (simulationState.type === 'technical') {
          if (simulationState.failedNodes.includes(d.id)) return '#f27272'; // Red
          if (simulationState.affectedNodes.includes(d.id)) return '#f2b84b'; // Orange/Amber
        } else if (simulationState.type === 'knowledge') {
          if (simulationState.unavailableEmployees.includes(d.id)) return '#f27272'; // Red
          if (simulationState.gaps.includes(d.id)) return '#f27272'; // Red Gap
        }
      }
      if (d.type === 'SYSTEM') return '#5b9cf2';
      if (d.type === 'COMPONENT') return '#f2b84b';
      if (d.type === 'EMPLOYEE') return '#b18af2';
      if (d.type === 'CAPABILITY') return '#4ade80';
      if (d.type === 'EVIDENCE') return '#f27272';
      return '#7a5f96';
    };

    nodeRef.current.select('circle')
      .attr('fill', d => getNodeColor(d))
      .attr('stroke', d => (selectedNodeId && d.id === selectedNodeId) ? '#fff' : '#0a0a0b');

    if (!selectedNodeId) {
      nodeRef.current.select('circle').attr('opacity', 1);
      nodeRef.current.selectAll('text').attr('opacity', 1);
      linkRef.current.attr('opacity', 0.6).attr('stroke', '#68675f').attr('stroke-width', 1.5);
    } else {
      nodeRef.current.select('circle').attr('opacity', d => neighbors.has(d.id) ? 1 : 0.18);
      nodeRef.current.selectAll('text').attr('opacity', d => neighbors.has(d.id) ? 1 : 0.15);
      
      linkRef.current
        .attr('opacity', d => {
          const sourceId = typeof d.source === 'object' ? d.source.id : d.source;
          const targetId = typeof d.target === 'object' ? d.target.id : d.target;
          return (sourceId === selectedNodeId || targetId === selectedNodeId) ? 0.95 : 0.06;
        })
        .attr('stroke', d => {
          const sourceId = typeof d.source === 'object' ? d.source.id : d.source;
          const targetId = typeof d.target === 'object' ? d.target.id : d.target;
          return (sourceId === selectedNodeId || targetId === selectedNodeId) ? '#eceae4' : '#68675f';
        })
        .attr('stroke-width', d => {
          const sourceId = typeof d.source === 'object' ? d.source.id : d.source;
          const targetId = typeof d.target === 'object' ? d.target.id : d.target;
          return (sourceId === selectedNodeId || targetId === selectedNodeId) ? 2.7 : 1.5;
        });
    }

  }, [selectedNodeId, simulationState, data]);

  return (
    <div ref={containerRef} style={{ width: '100%', height: '100%', backgroundColor: '#0a0a0b', backgroundImage: 'radial-gradient(#161618 1px, transparent 1px)', backgroundSize: '18px 18px' }}>
      <svg ref={svgRef} style={{ width: '100%', height: '100%' }}></svg>
    </div>
  );
};

export default GraphCanvas;
