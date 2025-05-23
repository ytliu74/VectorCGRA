"""
=========================================================================
CgraSystolicArrayRTL.py
=========================================================================

Author : Cheng Tan
  Date : Dec 22, 2024
"""

from ..controller.ControllerRTL import ControllerRTL
from ..lib.basic.val_rdy.ifcs import ValRdyRecvIfcRTL as RecvIfcRTL
from ..lib.basic.val_rdy.ifcs import ValRdySendIfcRTL as SendIfcRTL
from ..lib.opt_type import *
from ..lib.util.common import *
from ..mem.data.DataMemWithCrossbarRTL import DataMemWithCrossbarRTL
from ..noc.PyOCN.pymtl3_net.ocnlib.ifcs.positions import mk_ring_pos
from ..noc.PyOCN.pymtl3_net.ringnet.RingNetworkRTL import RingNetworkRTL
from ..tile.TileRTL import TileRTL


class CgraSystolicArrayRTL(Component):

  def construct(s, DataType, PredicateType, CtrlPktType, CgraPayloadType,
                CtrlSignalType, NocPktType, CgraIdType, cgra_id,
                width, height, ctrl_mem_size, data_mem_size_global,
                data_mem_size_per_bank, num_banks_per_cgra,
                num_registers_per_reg_bank, num_ctrl,
                total_steps, FunctionUnit, FuList, controller2addr_map,
                preload_data = None):

    multi_cgra_rows = 1
    multi_cgra_columns = 1
    num_cgras = multi_cgra_rows * multi_cgra_columns
    # Other topology can simply modify the tiles connections, or
    # leverage the template for modeling.
    s.num_mesh_ports = 4

    assert(width == 3)
    assert(height == 3)
    assert(num_banks_per_cgra == 4)
    s.num_tiles = width * height
    # An additional router for controller to receive CMD_COMPLETE signal from Ring to CPU.
    CtrlRingPos = mk_ring_pos(s.num_tiles + 1)
    CtrlAddrType = mk_bits(clog2(ctrl_mem_size))
    DataAddrType = mk_bits(clog2(data_mem_size_global))
    assert(data_mem_size_per_bank * num_banks_per_cgra <= \
           data_mem_size_global)

    # Interfaces
    s.recv_from_cpu_pkt = RecvIfcRTL(CtrlPktType)
    s.send_to_cpu_pkt = SendIfcRTL(CtrlPktType)
    s.recv_from_inter_cgra_noc = RecvIfcRTL(NocPktType)
    s.send_to_inter_cgra_noc = SendIfcRTL(NocPktType)

    # Interfaces on the boundary of the CGRA.
    s.recv_data_on_boundary_south = [RecvIfcRTL(DataType) for _ in range(width )]
    s.send_data_on_boundary_south = [SendIfcRTL(DataType) for _ in range(width )]
    s.recv_data_on_boundary_north = [RecvIfcRTL(DataType) for _ in range(width )]
    s.send_data_on_boundary_north = [SendIfcRTL(DataType) for _ in range(width )]

    s.recv_data_on_boundary_east  = [RecvIfcRTL(DataType) for _ in range(height)]
    s.send_data_on_boundary_east  = [SendIfcRTL(DataType) for _ in range(height)]
    s.recv_data_on_boundary_west  = [RecvIfcRTL(DataType) for _ in range(height)]
    s.send_data_on_boundary_west  = [SendIfcRTL(DataType) for _ in range(height)]

    # Components
    s.tile = [TileRTL(DataType, PredicateType, CtrlPktType,
                      CgraPayloadType, CtrlSignalType, ctrl_mem_size,
                      data_mem_size_global, num_ctrl,
                      total_steps, 4, 2,
                      s.num_mesh_ports,
                      s.num_mesh_ports,
                      num_cgras,
                      s.num_tiles,
                      num_registers_per_reg_bank,
                      FuList = FuList)
               for i in range(s.num_tiles)]
    idTo2d_map = {0: [0, 0]}
    s.data_mem = DataMemWithCrossbarRTL(NocPktType,
                                        CgraPayloadType,
                                        DataType,
                                        data_mem_size_global,
                                        data_mem_size_per_bank,
                                        num_banks_per_cgra,
                                        # 4 read/write from tiles and 1 read/write from NoC.
                                        # We actually only needs in total 3.
                                        4, 4,
                                        multi_cgra_rows,
                                        multi_cgra_columns,
                                        s.num_tiles,
                                        idTo2d_map,
                                        preload_data)
    s.controller = ControllerRTL(CgraIdType, CtrlPktType,
                                 NocPktType, DataType, DataAddrType,
                                 multi_cgra_rows,
                                 multi_cgra_columns,
                                 s.num_tiles,
                                 controller2addr_map,
                                 idTo2d_map)
    # An additional router for controller to receive CMD_COMPLETE signal from Ring to CPU.
    # The last argument of 1 is for the latency per hop.
    s.ctrl_ring = RingNetworkRTL(CtrlPktType, CtrlRingPos, s.num_tiles + 1, 1)

    # Address lower and upper bound.
    s.address_lower = InPort(DataAddrType)
    s.address_upper = InPort(DataAddrType)

    # Connections
    # Connects controller id.
    s.controller.cgra_id //= cgra_id
    s.data_mem.cgra_id //= cgra_id

    # Connects the address lower and upper bound.
    s.data_mem.address_lower //= s.address_lower
    s.data_mem.address_upper //= s.address_upper

    # Connects data memory with controller.
    s.data_mem.recv_raddr[4] //= s.controller.send_to_mem_load_request_addr
    s.data_mem.recv_from_noc_load_src_cgra //= s.controller.send_to_mem_load_request_src_cgra
    s.data_mem.recv_from_noc_load_src_tile //= s.controller.send_to_mem_load_request_src_tile
    s.data_mem.recv_waddr[4] //= s.controller.send_to_mem_store_request_addr
    s.data_mem.recv_wdata[4] //= s.controller.send_to_mem_store_request_data
    s.data_mem.recv_from_noc_rdata //= s.controller.send_to_tile_load_response_data
    s.data_mem.send_to_noc_load_request_pkt //= s.controller.recv_from_tile_load_request_pkt
    s.data_mem.send_to_noc_load_response_pkt //= s.controller.recv_from_tile_load_response_pkt
    s.data_mem.send_to_noc_store_pkt //= s.controller.recv_from_tile_store_request_pkt
    
    s.recv_from_inter_cgra_noc //= s.controller.recv_from_inter_cgra_noc
    s.send_to_inter_cgra_noc //= s.controller.send_to_inter_cgra_noc

    # Connects the ctrl interface between CPU and controller.
    s.recv_from_cpu_pkt //= s.controller.recv_from_cpu_pkt
    s.send_to_cpu_pkt //= s.controller.send_to_cpu_pkt

    # Assigns tile id.
    for i in range(s.num_tiles):
      s.tile[i].tile_id //= i
      s.tile[i].cgra_id //= cgra_id

    # Connects ring with each control memory.
    for i in range(s.num_tiles):
      s.ctrl_ring.send[i] //= s.tile[i].recv_from_controller_pkt
    s.ctrl_ring.send[s.num_tiles] //= s.controller.recv_from_ctrl_ring_pkt

    for i in range(s.num_tiles):
      s.ctrl_ring.recv[i] //= s.tile[i].send_to_controller_pkt
    s.ctrl_ring.recv[s.num_tiles] //= s.controller.send_to_ctrl_ring_pkt

    for i in range(s.num_tiles):

      if i // width > 0:
        s.tile[i].send_data[PORT_SOUTH] //= s.tile[i-width].recv_data[PORT_NORTH]

      if i // width < height - 1:
        s.tile[i].send_data[PORT_NORTH] //= s.tile[i+width].recv_data[PORT_SOUTH]

      if i % width > 0:
        s.tile[i].send_data[PORT_WEST] //= s.tile[i-1].recv_data[PORT_EAST]

      if i % width < width - 1:
        s.tile[i].send_data[PORT_EAST] //= s.tile[i+1].recv_data[PORT_WEST]

      if i // width == 0:
        s.tile[i].send_data[PORT_SOUTH] //= s.send_data_on_boundary_south[i % width]
        s.tile[i].recv_data[PORT_SOUTH] //= s.recv_data_on_boundary_south[i % width]

      if i // width == height - 1:
        s.tile[i].send_data[PORT_NORTH] //= s.send_data_on_boundary_north[i % width]
        s.tile[i].recv_data[PORT_NORTH] //= s.recv_data_on_boundary_north[i % width]

      if i % width == 0:
        s.tile[i].send_data[PORT_WEST] //= s.send_data_on_boundary_west[i // width]
        s.tile[i].recv_data[PORT_WEST] //= s.recv_data_on_boundary_west[i // width]

      if i % width == width - 1:
        s.tile[i].send_data[PORT_EAST] //= s.send_data_on_boundary_east[i // width]
        s.tile[i].recv_data[PORT_EAST] //= s.recv_data_on_boundary_east[i // width]

      # Memory banks are connected at bottom and right of the CGRA/systolic array.
      if i == 0 or i == 1 or i == 5 or i == 8:
        # Left-bottom tile.
        s.tile[0].to_mem_raddr   //= s.data_mem.recv_raddr[0]
        s.tile[0].from_mem_rdata //= s.data_mem.send_rdata[0]
        s.tile[0].to_mem_waddr   //= s.data_mem.recv_waddr[0]
        s.tile[0].to_mem_wdata   //= s.data_mem.recv_wdata[0]
  
        # Mid-bottom tile.
        s.tile[1].to_mem_raddr   //= s.data_mem.recv_raddr[1]
        s.tile[1].from_mem_rdata //= s.data_mem.send_rdata[1]
        s.tile[1].to_mem_waddr   //= s.data_mem.recv_waddr[1]
        s.tile[1].to_mem_wdata   //= s.data_mem.recv_wdata[1]
  
        # Right-mid tile.
        s.tile[5].to_mem_raddr   //= s.data_mem.recv_raddr[2]
        s.tile[5].from_mem_rdata //= s.data_mem.send_rdata[2]
        s.tile[5].to_mem_waddr   //= s.data_mem.recv_waddr[2]
        s.tile[5].to_mem_wdata   //= s.data_mem.recv_wdata[2]
  
        # Right-top tile.
        s.tile[8].to_mem_raddr   //= s.data_mem.recv_raddr[3]
        s.tile[8].from_mem_rdata //= s.data_mem.send_rdata[3]
        s.tile[8].to_mem_waddr   //= s.data_mem.recv_waddr[3]
        s.tile[8].to_mem_wdata   //= s.data_mem.recv_wdata[3]

      else:
        s.tile[i].to_mem_raddr.rdy   //= 0
        s.tile[i].from_mem_rdata.val //= 0
        s.tile[i].from_mem_rdata.msg //= DataType(0, 0)
        s.tile[i].to_mem_waddr.rdy   //= 0
        s.tile[i].to_mem_wdata.rdy   //= 0

  # Line trace
  def line_trace(s):
    res = "Controller: " + s.controller.line_trace() + "\n"
    res += "Ctrl Ring: " + s.ctrl_ring.line_trace() + "\n"
    res += "||\n\n".join([(("[tile"+str(i)+"]: ") + x.line_trace())
                       for (i,x) in enumerate(s.tile)])
    res += "\nData Memory: [" + s.data_mem.line_trace() + "]    \n"
    return res
